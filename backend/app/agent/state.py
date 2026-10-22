"""多 Agent 编排的状态结构（LangGraph 在各节点间传递的数据）。

注意：langgraph 0.0.20 不允许节点名与 state 字段同名，
因此 state 用语义名（intent / evidence），节点统一用 xxx_agent 命名。
"""
from typing import TypedDict


class AgentState(TypedDict, total=False):
    message: str        # 用户原始问题
    history: list       # 最近几轮对话（供工具选择时理解上下文）
    intent: str         # intent_agent 判定的意图（symptom/department/drug/knowledge/guide/general）
    evidence: list      # 证据列表，结构 {source, type, content}，直接回传给前端溯源
    symptoms: list      # 由证据推导的症状标签
    department: str     # 由证据推导的推荐科室
    context: str        # 拼给大模型的参考资料文本
    tool_log: list      # 工具调用记录 [{tool, ok, args, count, error}]，供评估算工具错误率
    safety: dict        # 确定性安全层字段 {disclaimer, medReminder}
