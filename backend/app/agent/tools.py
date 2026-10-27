"""工具层：把本地检索能力暴露给大模型自主调用（Tool Calling）。

与 P3-3 的差别：
  P3-3 是「代码固定调用两条检索路径」（先向量、再图谱，写死在流程里）；
  这里是「把工具清单交给模型」，由模型决定调哪个、传什么参数、要不要多轮。

工具执行结果同时用于两处：
  1. 回灌给模型（role=tool），让它判断还要不要继续查；
  2. 写进 evidence，供前端溯源与评估算召回指标。
"""
import json

from app.config import settings
from app.retrieval import hybrid
from app.retrieval.hybrid import VAGUE_ENTITIES
from app.services.llm import create_completion
from app.store import kg_store

MAX_TOOL_ROUNDS = 2     # 最多几轮工具调用，防止模型无休止查下去
TOOL_TOP_K = settings.TOOL_TOP_K   # 单次工具调用的返回条数（可配）

# 工具清单（OpenAI function calling schema）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "vector_search",
            "description": (
                "在本地医疗知识库做向量语义检索。适合用户用口语化描述症状或提问时使用，"
                "能把「头疼」「拉肚子」这类口语说法匹配到规范的医疗实体。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索语句，尽量保留用户原话"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kg_search",
            "description": (
                "按关键词在医疗知识图谱中做姓名级模糊搜索，返回匹配的实体（疾病/症状/药物/科室等）"
                "及其描述。适合已经知道大概实体名、想确认它在图谱里叫什么时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "实体关键词，如「头痛」「布洛芬」"},
                    "limit": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kg_expand",
            "description": (
                "查询某个医疗实体在知识图谱中的全部关联关系（常见症状、建议科室、病因、疗法、"
                "常用药物、副作用、禁忌人群、药物相互作用等），双向扩展。"
                "问「该挂什么科」「有什么副作用」「有什么禁忌」时必须用这个工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "图谱中的实体名，须精确"},
                },
                "required": ["entity"],
            },
        },
    },
]

TOOL_SYSTEM_PROMPT = (
    "你是医疗知识库的检索调度器。根据用户问题，调用最合适的工具去本地知识库取资料。"
    "只做检索，不要直接回答问题，也不要编造知识库外的内容。"
    "如果一个问题需要多类信息（例如既要知道该挂什么科、又要知道用什么药），"
    "可以在同一轮里调用多个工具。"
)


# ---------------- 工具执行体 ----------------

def _exec_vector_search(query: str) -> list:
    """向量语义检索。带上相似度分数 —— 上层据此判断命中是否可靠、能不能当症状标签。"""
    results = hybrid.vector_search(query, top_k=TOOL_TOP_K)
    return [
        {"source": "vector", "type": r["type"], "content": r["content"],
         "entity": r["entity"], "relation": "", "target": "",
         "score": r.get("score")}
        for r in results
    ]


def _exec_kg_search(keyword: str, limit: int = 5) -> list:
    """图谱关键词搜索（过滤空泛枢纽实体）。"""
    rows = kg_store.search_nodes(keyword, limit)
    return [
        {"source": "kg", "type": r["type"], "content": r["desc"] or r["name"],
         "entity": r["name"], "relation": "", "target": ""}
        for r in rows if r["name"] not in VAGUE_ENTITIES
    ]


def _exec_kg_expand(entity: str) -> list:
    """图谱双向关系扩展。

    过滤空泛枢纽实体：「高血压 -> 药物治疗」「高血压 -> 所有人群」这类三元组
    每个病都有、却零信息量，进证据只会占位并稀释上下文。
    """
    triples = kg_store.get_triples(entity)
    return [
        {"source": "kg", "type": t["relation"],
         "content": f"{t['entity']} -> {t['related']}",
         "entity": t["entity"], "relation": t["relation"], "target": t["related"]}
        for t in triples if t["related"] not in VAGUE_ENTITIES
    ]


_EXECUTORS = {
    "vector_search": _exec_vector_search,
    "kg_search": _exec_kg_search,
    "kg_expand": _exec_kg_expand,
}


# ---------------- 工具调用循环 ----------------

def call_tools(message: str, branch_hint: str = "", history: list | None = None):
    """让模型自主选择并调用工具，把结果回灌后再给模型一次机会。

    branch_hint：当前分支的提示（例如「用户问用药，优先查适应症/副作用/禁忌」），
    用来引导模型优先选合适的工具，但不限制它只能调某一个。

    返回 (evidence_items, tool_log, final_text)
    """
    system = TOOL_SYSTEM_PROMPT
    if branch_hint:
        system = f"{system}\n\n当前问题类型提示：{branch_hint}"

    messages = [{"role": "system", "content": system}]
    messages.extend((history or [])[-4:])          # 只带最近两轮，避免上下文过长
    messages.append({"role": "user", "content": message})

    evidence, tool_log, final_text = [], [], ""

    for _ in range(MAX_TOOL_ROUNDS):
        # 必须走统一入口：裸 client 调用会绕过超时与熔断
        resp = create_completion(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )
        msg = resp.choices[0].message
        calls = msg.tool_calls or []

        if not calls:                              # 模型认为不需要再查了
            final_text = msg.content or ""
            break

        # assistant 的 tool_calls 回写成 dict，避免 SDK 对象序列化的版本差异
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in calls
            ],
        })

        for tc in calls:
            name = tc.function.name
            args, ok, err, items = {}, True, "", []
            try:
                args = json.loads(tc.function.arguments or "{}")
                items = _EXECUTORS[name](**args)
            except KeyError:
                ok, err = False, f"未知工具 {name}"
            except Exception as e:
                ok, err = False, f"{type(e).__name__}: {e}"

            evidence.extend(items)
            tool_log.append({"tool": name, "ok": ok, "args": args,
                             "count": len(items), "error": err})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(items if ok else [{"error": err}], ensure_ascii=False),
            })

    return evidence, tool_log, final_text
