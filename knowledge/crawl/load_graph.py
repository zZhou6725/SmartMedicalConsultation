"""把抓取到的疾病数据写入 Neo4j。

设计：
  · 幂等 MERGE（按 标签+name 合并节点，按关系类型合并边），可反复执行；
  · **不清空已有数据** —— 原来的 47 条种子数据保留，爬取数据叠加进去，
    这样评估金标集里引用的实体（偏头痛/高血压/布洛芬…）不会被抹掉；
  · 关系类型与标签只取自 FIELD_MAP 白名单（不在参数里拼字符串，避免注入）。

用法：
    python knowledge/crawl/load_graph.py --dry-run    # 只统计将要写入什么
    python knowledge/crawl/load_graph.py              # 实际写入
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase                     # noqa: E402

from app.config import settings                     # noqa: E402

SRC = ROOT / "data" / "raw" / "diseases.json"
BATCH = 500

# 允许写入的标签与关系（白名单，来自爬虫的 FIELD_MAP）
ALLOWED = {
    ("Department", "BELONG_DEPARTMENT"),
    ("Symptom", "HAS_SYMPTOM"),
    ("Drug", "USE_DRUG"),
    ("Crowd", "FIT_CROWD"),
    ("Cure", "HAS_CURE"),
    ("Disease", "BELONG_DISEASE"),
    ("Check", "HAS_CHECK"),
}


def load_rows() -> tuple[dict, list]:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    diseases = data.get("diseases") or []
    rows = defaultdict(list)          # (label, rel) -> [{disease, target}]
    for d in diseases:
        name = d["name"]
        for r in d.get("relations") or []:
            key = (r["type"], r["relation"])
            if key not in ALLOWED:
                continue
            for t in r["targets"]:
                if t and t != name:
                    rows[key].append({"disease": name, "target": t})
    return data, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data, rows = load_rows()
    print(f"源文件：{SRC}")
    print(f"疾病数：{data.get('diseaseCount')}　抓取时间：{data.get('crawledAt')}")
    total_edges = sum(len(v) for v in rows.values())
    print(f"待写入关系：{total_edges} 条")
    for (label, rel), v in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        uniq = len({x["target"] for x in v})
        print(f"  {label:12} -[{rel:18}]-> {len(v):6} 条（去重实体 {uniq}）")

    if args.dry_run:
        print("\n--dry-run：未写入")
        return

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    # 先给所有涉及的标签建唯一约束（幂等），避免重复节点
    labels = {"Disease"} | {lab for lab, _ in rows}
    with driver.session() as s:
        for lab in sorted(labels):
            s.run(f"CREATE CONSTRAINT {lab.lower()}_name IF NOT EXISTS "
                  f"FOR (n:{lab}) REQUIRE n.name IS UNIQUE")

    written = 0
    with driver.session() as s:
        for (label, rel), items in rows.items():
            if (label, rel) not in ALLOWED:
                continue
            cypher = (
                "UNWIND $rows AS row "
                "MERGE (d:Disease {name: row.disease}) "
                f"MERGE (t:{label} {{name: row.target}}) "
                f"MERGE (d)-[:{rel}]->(t)"
            )
            for i in range(0, len(items), BATCH):
                s.run(cypher, rows=items[i:i + BATCH])
            written += len(items)
            print(f"  ✓ {label} -[{rel}]-> {len(items)} 条")

        counts = s.run(
            "MATCH (n) WITH labels(n)[0] AS t, count(*) AS c "
            "RETURN t, c ORDER BY c DESC").data()
        rels = s.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c "
            "ORDER BY c DESC").data()

    driver.close()
    print(f"\n已写入 {written} 条关系")
    print("当前图谱节点：", {r["t"]: r["c"] for r in counts})
    print("当前图谱关系：", {r["t"]: r["c"] for r in rels})


if __name__ == "__main__":
    main()
