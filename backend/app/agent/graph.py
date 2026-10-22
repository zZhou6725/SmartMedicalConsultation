"""LangGraph 多 Agent 编排（P3-4）。

流程：

                     ┌─ symptom_agent   （症状检测）
                     ├─ department_agent（科室推荐）
     intent_agent ───┼─ drug_agent      （用药建议）      ┌────────────┐
     （意图识别）     ├─ knowledge_agent （医学知识）  ──→ │ safety_agent│ ──→ END
                     ├─ guide_agent     （就医指导）      │ （安全检查） │
                     └─ general_agent   （通用对话）      └────────────┘

设计说明：
  · 意图识别用确定性关键词规则（见 nodes.classify_intent），控制流优先可控；
  · 五个医疗分支内部用大模型做 Tool Calling，由模型自己决定调哪个检索工具；
  · 所有分支最终强制汇聚到 safety_agent，保证免责声明/用药提醒 100% 覆盖；
  · 最终答案的流式生成留在 api/chat.py —— 图只负责「决策与取证」，
    生成交给 llm 层走 SSE，避免在节点里做 token 级流式带来的复杂度。
"""
from functools import lru_cache

from langgraph.graph import END, StateGraph

from app.agent import nodes
from app.agent.state import AgentState

# 意图 → 分支节点名（同时作为条件边的目标映射）
BRANCH_NODES = {
    "symptom": "symptom_agent",
    "department": "department_agent",
    "drug": "drug_agent",
    "knowledge": "knowledge_agent",
    "guide": "guide_agent",
    "general": "general_agent",
}


def _route(state) -> str:
    """条件边：按意图路由，未知意图一律回落到通用对话。"""
    intent = state.get("intent") or "general"
    return intent if intent in BRANCH_NODES else "general"


@lru_cache(maxsize=1)
def build_graph():
    """构建并编译状态图（进程内只编译一次）。"""
    g = StateGraph(AgentState)

    g.add_node("intent_agent", nodes.intent_agent)
    g.add_node("symptom_agent", nodes.symptom_agent)
    g.add_node("department_agent", nodes.department_agent)
    g.add_node("drug_agent", nodes.drug_agent)
    g.add_node("knowledge_agent", nodes.knowledge_agent)
    g.add_node("guide_agent", nodes.guide_agent)
    g.add_node("general_agent", nodes.general_agent)
    g.add_node("safety_agent", nodes.safety_agent)

    g.set_entry_point("intent_agent")
    g.add_conditional_edges("intent_agent", _route, BRANCH_NODES)

    # 医疗分支与通用对话都强制汇聚安全检查
    for node in BRANCH_NODES.values():
        g.add_edge(node, "safety_agent")
    g.add_edge("safety_agent", END)

    return g.compile()


def run_agent(message: str, history: list | None = None) -> AgentState:
    """跑一遍编排，返回最终状态（intent/evidence/context/symptoms/department/safety）。"""
    graph = build_graph()
    return graph.invoke({
        "message": message,
        "history": history or [],
        "tool_log": [],
    })
