"""多 Agent 节点实现：意图识别 + 五路医疗分支 + 安全检查。

节点命名统一为 xxx_agent，因为 langgraph 0.0.20 禁止节点名与 state 字段同名。
"""
from app.agent import tools
from app.retrieval import hybrid
from app.services.safety import detect_emergency, safety_fields

# 意图关键词表：列表顺序即优先级，越具体的意图排越前
# （"头痛吃什么药" 同时命中症状与用药，应判为 drug —— 用药需求更明确）
INTENT_RULES = [
    ("drug", [
        "药", "服用", "口服", "剂量", "几片", "胶囊", "片剂", "冲剂",
        "布洛芬", "阿莫西林", "二甲双胍", "奥美拉唑", "氨氯地平", "对乙酰氨基酚",
        "抗生素", "止痛", "消炎", "退烧", "副作用", "禁忌", "相互作用",
    ]),
    ("department", ["挂什么科", "挂号", "看哪科", "哪个科", "什么科室", "就诊科", "科室"]),
    ("guide", ["要不要去医院", "需要就医", "什么时候去", "急诊", "急救",
               "多久能好", "严不严重", "严重吗", "会死吗"]),
    # 定义型问句优先于「实体名里恰好含症状词」的表层匹配：
    # 「偏头痛是什么」不该因为含「头痛」就被判成症状咨询
    ("knowledge", ["是什么", "什么是", "有哪些", "介绍", "科普", "区别", "原理",
                   "预防", "后遗症", "怎么治", "怎么护理", "需要手术", "有风险"]),
    ("symptom", ["症状", "头疼", "头痛", "发烧", "发热", "咳嗽", "恶心", "呕吐",
                 "头晕", "腹痛", "胃痛", "胃部不适", "不舒服", "反酸", "胃胀",
                 "腹胀", "腹泻", "便秘", "乏力", "水肿", "流鼻涕", "不适",
                 "口渴", "多尿", "消瘦", "体重下降",
                 "疼", "痛", "痒", "失眠"]),
    # 因果型问句放在症状之后：「最近老是头晕是怎么回事」更可能是症状咨询
    ("knowledge", ["怎么回事", "为什么", "原因", "病因"]),
]

# 医疗分支检索不到内容时注入的占位上下文。
# 作用：让 llm.build_messages 里的 grounded 约束生效，强制模型说「资料未覆盖、请就医」，
# 而不是凭参数记忆编造答案。
EMPTY_CONTEXT = "参考资料：本地医疗知识库中未检索到与该问题相关的内容。"

# 各医疗分支给工具调度器的提示（引导优先用合适的工具，但不限制只能调一个）
BRANCH_HINTS = {
    "symptom": "用户在描述症状。优先用 vector_search 找到可能的疾病，再用 kg_expand 展开该疾病的症状、科室、用药。",
    "department": "用户想知道该挂哪个科。优先用 kg_expand 查实体的 BELONG_DEPARTMENT 关系；实体名不确定时先用 kg_search 或 vector_search 确认。",
    "drug": "用户在问用药。优先用 kg_expand 查药物的适应症、副作用、禁忌人群、相互作用；药名不确定时先 kg_search。",
    "knowledge": "用户在问医学知识。优先用 vector_search 做语义检索，必要时用 kg_expand 补充实体关系。",
    "guide": "用户关心就医时机或严重程度。先用 vector_search / kg_search 定位相关疾病，再用 kg_expand 取科室信息，供后续给出就医指引。",
    "general": "",
}


def classify_intent(message: str) -> str:
    """意图识别：急症优先 → 关键词规则 → 图谱实体名兜底 → general。

    为什么用规则而不是让大模型分类：意图决定**控制流**（走哪条分支），
    可控性与可测试性优先；模型的不确定性留给更需要判断力的工具选择环节。
    """
    text = (message or "").lower()

    # 急症优先：不管用户怎么问（"胸痛怎么办"/"胸口疼得厉害"），
    # 一律走就医指导分支，避免被「疼」这类泛症状词吞掉
    if detect_emergency(text)["hit"]:
        return "guide"

    for intent, keywords in INTENT_RULES:
        if any(k in text for k in keywords):
            return intent

    # 实体兜底：问题里直接出现图谱实体名（如「我高血压」「布洛芬怎么样」），
    # 说明这是医疗问题，绝不能落到 general —— 那条分支既不检索、也不受
    # grounded 约束，模型会凭参数记忆自由作答（这是幻觉入口）。
    if any(name in text for name in _entity_names()):
        return "knowledge"

    return "general"


def _dedup(items: list) -> list:
    """按 content 去重，保持首次出现的顺序（越靠前越相关）。"""
    seen, out = set(), []
    for item in items:
        key = item.get("content", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# ---------------- 图谱实体名兜底 ----------------

# 用可变容器做缓存：查询失败时不写缓存，下次还能重试（lru_cache 会把失败也缓存住）
_ENTITY_CACHE = {"names": ()}


def _entity_names() -> tuple:
    """图谱里的全部实体名，供意图识别做兜底匹配。

    「我高血压」「布洛芬怎么样」这类问法不含任何意图关键词，
    但实体名一定在图谱里 —— 用它兜底比不断往关键词表里加词更可维护。
    """
    if _ENTITY_CACHE["names"]:
        return _ENTITY_CACHE["names"]
    try:
        from app.store import kg_store

        rows = kg_store.run_read(
            "MATCH (n) WHERE n.name IS NOT NULL RETURN n.name AS name"
        )
        _ENTITY_CACHE["names"] = tuple(r["name"] for r in rows if r.get("name"))
    except Exception:
        return ()
    return _ENTITY_CACHE["names"]


# 检索相关性下限：低于此分数的命中视为噪声，不作为症状标签 / 科室依据。
# 实测依据：真命中 top1 在 0.67 上下，而「喉咙痛」这类图谱未覆盖的问题 top1 只有 0.53；
# 不加下限就会把「胃痛 / 头痛 / 咳嗽」当成用户描述的症状标签展示出去。
RELEVANCE_FLOOR = 0.60


def _derive(evidence: list):
    """从证据推症状标签与推荐科室。

    symptoms：类型为 symptom 且分数达标的实体名。
    department：优先取图谱 BELONG_DEPARTMENT 关系的终点；没有退而取向量命中的科室实体。

    整体分数不达标时直接返回空 —— 宁可少显示，也不能显示错。
    """
    scores = [e["score"] for e in evidence if e.get("score") is not None]
    if scores and max(scores) < RELEVANCE_FLOOR:
        return [], ""

    symptoms = [e.get("entity", "") for e in evidence
                if e.get("type") == "symptom" and e.get("entity")
                and (e.get("score") is None or e["score"] >= RELEVANCE_FLOOR)]

    department = next((e.get("target", "") for e in evidence
                       if e.get("relation") == "BELONG_DEPARTMENT"), "")
    if not department:
        department = next((e.get("entity", "") for e in evidence
                           if e.get("type") == "department" and e.get("entity")
                           and (e.get("score") or 0) >= RELEVANCE_FLOOR), "")
    return symptoms[:3], department


def _fallback_items(message: str) -> list:
    """兜底证据：模型一轮工具都没调（或全失败）时，退回 P3-3 的固定混合检索。

    保证「回答必须有证据」这条不因为模型抽风而丢掉。
    """
    data = hybrid.hybrid_search(message, tools.TOOL_TOP_K)
    items = [
        {"source": "vector", "type": r["type"], "content": r["content"],
         "entity": r["entity"], "relation": "", "target": "",
         "score": r.get("score")}
        for r in data["vectorResults"]
    ]
    items += [
        {"source": "kg", "type": g["relation"], "content": g["content"],
         "entity": g["entity"], "relation": g["relation"], "target": g["related"]}
        for g in data["graphResults"]
    ]
    return items


def _medical_agent(state, branch: str):
    """五路医疗分支共用的执行体：工具调用 → 证据 → 拼上下文。"""
    message = state.get("message", "")
    evidence, tool_log, _ = tools.call_tools(
        message, BRANCH_HINTS.get(branch, ""), state.get("history") or []
    )
    evidence = _dedup(evidence)

    if not evidence:                                   # 兜底
        try:
            evidence = _dedup(_fallback_items(message))
            tool_log = (tool_log or []) + [{"tool": "hybrid_fallback", "ok": True,
                                            "args": {"query": message},
                                            "count": len(evidence), "error": ""}]
        except Exception:
            evidence = []

    symptoms, department = _derive(evidence)
    public_evidence = [
        {"source": e["source"], "type": e["type"], "content": e["content"]}
        for e in evidence
    ]

    context = hybrid.build_context(public_evidence)
    if not context:
        # 检索不到内容时也必须给模型一个明确的「无资料」信号。
        # 否则 context 为空 → grounded 约束不会注入 → 模型会凭参数记忆自由作答，
        # 这是最危险的幻觉入口（评估里 sy08 / oo06 就是这样漏出去的）。
        context = EMPTY_CONTEXT

    return {
        "evidence": public_evidence,
        "context": context,
        "symptoms": symptoms,
        "department": department,
        "tool_log": tool_log,
    }


# ---------------- 六个分支节点 ----------------

def intent_agent(state):
    """意图识别。"""
    return {"intent": classify_intent(state.get("message", ""))}


def symptom_agent(state):
    return _medical_agent(state, "symptom")


def department_agent(state):
    return _medical_agent(state, "department")


def drug_agent(state):
    return _medical_agent(state, "drug")


def knowledge_agent(state):
    return _medical_agent(state, "knowledge")


def guide_agent(state):
    return _medical_agent(state, "guide")


def general_agent(state):
    """通用对话：不检索、不调工具。"""
    return {"evidence": [], "context": "", "symptoms": [],
            "department": "", "tool_log": []}


def safety_agent(state):
    """安全检查（强制汇聚点）：确定性规则，不依赖大模型。

    比开发方案的要求更严格一点 —— 通用对话也走这里，
    让「免责声明 100% 覆盖」成为结构性保证，而不是靠调用方记得加。
    """
    return {"safety": safety_fields(state.get("message", ""))}
