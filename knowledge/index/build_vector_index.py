"""从 Neo4j 知识图谱构建 FAISS 向量索引（P3-1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # knowledge/ → relation_labels

from neo4j import GraphDatabase                          # noqa: E402

from app.config import settings                          # noqa: E402
from app.retrieval.embeddings import encode              # noqa: E402
from app.retrieval import vector_store as vs             # noqa: E402
# 关系类型 → 中文说明：让检索文本更"像人话"，语义匹配更准（与 desc 回填脚本共用）
from relation_labels import REL_CN                       # noqa: E402

# 取每个节点 + 它的所有出边（关系类型|目标名）
CYPHER = """
MATCH (n)
WHERE n.name IS NOT NULL
OPTIONAL MATCH (n)-[r]->(m)
WITH n, collect(type(r) + '|' + coalesce(m.name, '')) AS rels
RETURN labels(n)[0] AS type, n.name AS name, n.desc AS desc, rels
"""


def build_text(node_type: str, name: str, rels: list) -> str:
    """把一个实体拼成自然语言描述，例如：
    感冒（Disease）：常见症状发热；常见症状咳嗽；建议科室呼吸内科
    """
    parts = []
    for item in rels:
        if not item:                       # 无关系的节点会带一个空串，跳过
            continue
        rel, _, target = item.partition("|")
        parts.append(f"{REL_CN.get(rel, rel)}{target}")
    tail = "；".join(parts)
    return f"{name}（{node_type}）：{tail}" if tail else f"{name}（{node_type}）"


def main():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    with driver.session() as session:
        rows = session.run(CYPHER).data()
    driver.close()

    metas, texts = [], []
    for row in rows:
        # 优先用节点 desc（含出边+入边，是完整语义句）；未回填时退回只拼出边的旧格式
        text = row.get("desc") or build_text(row["type"], row["name"], row["rels"])
        texts.append(text)
        metas.append({"type": row["type"], "entity": row["name"], "content": text})

    print(f"实体数: {len(texts)}")
    for t in texts[:3]:
        print("  样例:", t)

    vecs = encode(texts)                       # 批量编码
    vs.build(vecs, metas)                      # 建索引并保存
    print(f"✅ 索引已保存，条数: {len(texts)}  维度: {vecs.shape[1]}")


if __name__ == "__main__":
    main()