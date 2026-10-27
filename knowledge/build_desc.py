"""回填 Neo4j 节点的 desc（一句话描述），供向量索引与接口 15/16 使用。

做法：只把图谱里**已存在的关系**拼成一句话，不引入任何外部医学知识。
  出边用 REL_CN（「常见症状发热」），入边用 REV_CN（「可见于感冒、肺炎」）——
  叶子节点（症状/科室/药品）只有入边，不处理入边的话它们的 desc 只能是裸名字。

读写分离：写库只出现在初始化/构建脚本里，API 侧一律走 kg_store.run_read 只读防护。

用法：
    python knowledge/build_desc.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "knowledge"))      # → relation_labels

from neo4j import GraphDatabase                   # noqa: E402

from app.config import settings                   # noqa: E402
from relation_labels import REL_CN, REV_CN        # noqa: E402

# 取每个节点的出边（关系|目标名）与入边（关系|来源名）
CYPHER = """
MATCH (n)
WHERE n.name IS NOT NULL
OPTIONAL MATCH (n)-[r]->(m)
WITH n, collect(type(r) + '|' + coalesce(m.name, '')) AS out_rels
OPTIONAL MATCH (src)-[r2]->(n)
WITH n, out_rels, collect(type(r2) + '|' + coalesce(src.name, '')) AS in_rels
RETURN n.name AS name, labels(n)[0] AS type, out_rels, in_rels
"""

# 回写：按 name + 标签双重匹配，避免同名跨标签误写
WRITE_CYPHER = """
UNWIND $rows AS row
MATCH (n) WHERE n.name = row.name AND labels(n)[0] = row.type
SET n.desc = row.desc
RETURN count(n) AS c
"""


MAX_OUT = 12    # 出边最多列几项
MAX_IN = 8      # 每种反向关系最多列几项（「发热」可见于上百种病，全列会稀释语义）


def build_desc(name: str, out_rels: list, in_rels: list) -> str:
    """把关系列表拼成一句话描述，例如：

    偏头痛：适用人群青年女性；建议科室神经内科；常见症状头痛
    头痛：可见于感冒、肺炎、偏头痛、高血压；可用药物有布洛芬
    """
    parts = []

    # 出边：常见症状发热 / 建议科室呼吸内科 …
    for item in out_rels[:MAX_OUT]:
        if not item:                       # 无关系的节点会带一个空串，跳过
            continue
        rel, _, target = item.partition("|")
        parts.append(f"{REL_CN.get(rel, rel)}{target}")

    # 入边：同一种反向关系合并成一句，避免重复啰嗦
    grouped = {}
    for item in in_rels:
        if not item:
            continue
        rel, _, src = item.partition("|")
        phrase = REV_CN.get(rel, f"与{REL_CN.get(rel, rel)}相关的有")
        grouped.setdefault(phrase, []).append(src)
    for phrase, srcs in grouped.items():
        more = "等" if len(srcs) > MAX_IN else ""
        parts.append(f"{phrase}{'、'.join(srcs[:MAX_IN])}{more}")

    return f"{name}：{'；'.join(parts)}" if parts else name


def main():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    with driver.session() as session:
        rows = session.run(CYPHER).data()

    payload = [
        {"name": r["name"], "type": r["type"],
         "desc": build_desc(r["name"], r["out_rels"], r["in_rels"])}
        for r in rows
    ]

    with driver.session() as session:
        written = session.run(WRITE_CYPHER, rows=payload).single()["c"]

    driver.close()

    enriched = sum(1 for p in payload if p["desc"] != p["name"])
    print(f"节点总数: {len(payload)}   已写入 desc: {written}   有实质描述: {enriched}")
    for p in payload[:3]:
        print(f"  [{p['type']}] {p['desc'][:90]}")


if __name__ == "__main__":
    main()
