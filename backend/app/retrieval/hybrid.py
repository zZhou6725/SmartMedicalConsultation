"""GraphRAG 混合检索（P3-3 / 接口12）。

两路召回后合并：
  向量路：BGE-M3 编码 → FAISS 内积召回，负责「口语化问题 → 规范医疗实体」的模糊匹配；
  图谱路：以向量命中的实体为种子，在 Neo4j 中扩展一跳双向三元组，
          负责把实体周围的结构化事实（症状/科室/用药/禁忌）摊开给上层用。

为什么要两路：向量擅长语义相近，但只知道「哪些实体相关」；图谱知道「实体之间的关系」，
但需要精确的实体名才能查。先向量找种子、再图谱摊开关系，正好互补。
"""
from app.retrieval.embeddings import encode
from app.retrieval import vector_store as vs
from app.store import kg_store

# 取前 N 个向量命中作为图谱扩展种子
SEED_TOP_N = 5

# 空泛实体：度数极高但信息量极低（「药物治疗」挂了 500 个疾病），
# 任何带「治疗」的提问都会把它们顶上来白占 Top-K 名额，因此不进检索证据。
VAGUE_ENTITIES = {
    "药物治疗", "手术治疗", "所有人群", "各年龄段", "成年人", "中老年", "中老年人",
    "青中年人", "年轻女性", "女性", "男性", "儿童", "老年人", "就医", "医生", "记者",
}

# 词面命中加成：查询里直接出现了实体名，是强于余弦相似度的信号
LEXICAL_BOOST = 0.15

# 同族判定阈值（字符级 Jaccard）
FAMILY_JACCARD = 0.7

# 中文医疗口语归一化：同一个概念常有「疼/痛」两种写法
# （偏头疼 ≡ 偏头痛、神经性头疼 ≡ 神经性偏头痛），不归一化会被当成两个不同实体。
_SYNONYM_MAP = {"疼": "痛"}


def _norm(name: str) -> str:
    for a, b in _SYNONYM_MAP.items():
        name = name.replace(a, b)
    return name


def _is_family_dup(name: str, kept: list) -> bool:
    """判断 name 是否与已保留的某个实体属同一族（近义/包含/字符高度重合）。

    知识库扩大后，同一个概念会散成多个近义实体
    （偏头痛 / 偏头疼 / 一侧的头部疼痛 / 单侧的剧烈头痛），
    它们会把 Top-K 名额占满，导致真正要的那个排到第 5 名之后。
    比较前先做口语归一化，否则「偏头疼」与「偏头痛」只差一个字也会漏判。
    """
    n = _norm(name)
    for k in kept:
        kn = _norm(k)
        if n in kn or kn in n:
            return True
        a, b = set(n), set(kn)
        if a and b and len(a & b) / len(a | b) >= FAMILY_JACCARD:
            return True
    return False


def vector_search(query: str, top_k: int = 10) -> list:
    """向量语义召回（接口13 的核心逻辑）。

    三步后处理（知识库扩到 2000+ 实体后必不可少）：
      1. 过滤空泛实体（VAGUE_ENTITIES）；
      2. 词面命中加成 —— 查询里直接出现的实体名加权；
      3. 同族去重 —— 近义实体只保留排最前的那个，避免霸占名额。
    候选先多取 3 倍，才有余量做去重。
    """
    hits = vs.search(encode(query), top_k=max(top_k * 3, 15))
    q = query or ""

    scored = []
    for h in hits:
        meta = h["meta"]
        name = meta.get("entity", "")
        if not name or name in VAGUE_ENTITIES:
            continue
        score = float(h["score"]) + (LEXICAL_BOOST if name in q else 0.0)
        scored.append({
            "entity": name,
            "type": (meta.get("type", "") or "").lower(),   # Disease → disease
            "score": round(score, 4),
            "content": meta.get("content", ""),
        })

    scored.sort(key=lambda x: -x["score"])

    out, kept = [], []
    for r in scored:
        if _is_family_dup(r["entity"], kept):
            continue
        kept.append(r["entity"])
        out.append(r)
        if len(out) >= top_k:
            break
    return out


def graph_expand(seeds: list, top_k: int = 10) -> list:
    """以向量命中实体为种子扩展图谱三元组，按 (起点, 关系, 终点) 去重。

    seeds 需按相关度从高到低传入，函数保持该顺序，保证高相关种子的证据排在前。
    """
    seen, out = set(), []
    for seed in seeds:
        name = seed.get("entity") or ""
        if not name:
            continue
        try:
            triples = kg_store.get_triples(name)
        except Exception:
            continue                      # 单个种子查失败不影响整路检索
        for t in triples:
            # 空泛枢纽实体（药物治疗/所有人群…）在向量路已过滤，图谱路也必须过滤：
            # 它们连着的疾病最多，但不提供任何可用信息，进证据只会稀释上下文。
            if t["related"] in VAGUE_ENTITIES:
                continue
            key = (t["entity"], t["relation"], t["related"])
            if key in seen:
                continue
            seen.add(key)
            t["content"] = f"{t['entity']} -> {t['related']}"
            out.append(t)
            if len(out) >= top_k:
                return out
    return out


def hybrid_search(query: str, top_k: int = 10) -> dict:
    """GraphRAG 混合检索：向量召回 + 图谱扩展，返回两路结果。"""
    vec = vector_search(query, top_k)
    graph = graph_expand(vec[:SEED_TOP_N], top_k)
    return {
        "query": query,
        "vectorResults": vec,
        "graphResults": graph,
        "total": len(vec) + len(graph),
    }


def evidence_from(data: dict) -> list:
    """把一次混合检索结果压成对话层的证据列表（接口4/5 的 evidence 结构：source / type / content）。

    source=vector 时 type 为实体类型；source=kg 时 type 为关系类型。
    独立成函数是为了让对话层一次 hybrid_search 同时拿到证据、症状标签与推荐科室，
    避免重复检索。
    """
    evidence = [
        {"source": "vector", "type": r["type"], "content": r["content"]}
        for r in data["vectorResults"]
    ]
    evidence += [
        {"source": "kg", "type": r["relation"], "content": r["content"]}
        for r in data["graphResults"]
    ]
    return evidence


def build_evidence(query: str, top_k: int = 5) -> list:
    """便捷入口：检索 + 转证据一步到位。"""
    return evidence_from(hybrid_search(query, top_k))


def build_context(evidence: list) -> str:
    """把证据拼成 prompt 里的一段上下文文本。无证据时返回空串。"""
    if not evidence:
        return ""
    lines = [f"{i}. {e['content']}" for i, e in enumerate(evidence, 1)]
    return "参考资料（来自本地医疗知识库，请只依据以下资料作答）：\n" + "\n".join(lines)
