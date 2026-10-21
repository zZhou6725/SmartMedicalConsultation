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

# 取前 N 个向量命中作为图谱扩展种子（全部 47 个都扩展会引入大量噪声）
SEED_TOP_N = 5


def vector_search(query: str, top_k: int = 10) -> list:
    """向量语义召回（接口13 的核心逻辑，供混合检索与独立接口共用）。"""
    hits = vs.search(encode(query), top_k=top_k)
    return [
        {
            "entity": h["meta"].get("entity", ""),
            "type": (h["meta"].get("type", "") or "").lower(),   # Disease → disease
            "score": round(h["score"], 4),
            "content": h["meta"].get("content", ""),
        }
        for h in hits
    ]


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
