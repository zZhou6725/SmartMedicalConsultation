"""图谱清洗：删掉爬取过程中混入的脏实体与噪声关系。

三类问题（都来自爬取页面的脏数据，不是解析错误）：
  1. 脏实体：Crowd 类型里出现「医生」「记者」这种非人群词；
  2. 单字实体：「胀」「心」「肺」「水」「口」「血」「尿」—— 页面切分残留；
  3. 噪声关系：BELONG_DISEASE 里 94.7% 是单向边，且大量无交集
     （如「噬血细胞综合征 → 高血压」）。保留规则：
     双向边全留；单向边只有在**两个疾病共享至少一个症状**时才留。

用法：
    python knowledge/crawl/clean_graph.py --dry-run
    python knowledge/crawl/clean_graph.py
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase                     # noqa: E402

from app.config import settings                     # noqa: E402

# 明确不是医疗实体的词（爬取页面上的栏目/人物词）
BLACKLIST = ["医生", "记者", "专家", "患者", "医院", "查看更多"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    report = {}

    with driver.session() as s:
        # —— 预览 ——
        report["blacklist_nodes"] = s.run(
            "MATCH (n) WHERE n.name IN $names RETURN labels(n)[0] AS type, n.name AS name",
            names=BLACKLIST).data()
        report["one_char_nodes"] = s.run(
            "MATCH (n) WHERE size(n.name) = 1 RETURN labels(n)[0] AS type, n.name AS name").data()

        noisy = s.run(
            """
            MATCH (a:Disease)-[r:BELONG_DISEASE]->(b:Disease)
            WHERE NOT EXISTS { MATCH (b)-[:BELONG_DISEASE]->(a) }
              AND NOT EXISTS { MATCH (a)-[:HAS_SYMPTOM]->(x)<-[:HAS_SYMPTOM]-(b) }
            RETURN count(r) AS c
            """).single()["c"]
        total = s.run(
            "MATCH (:Disease)-[r:BELONG_DISEASE]->(:Disease) RETURN count(r) AS c"
        ).single()["c"]
        report["belong_disease"] = {"total": total, "noise_to_delete": noisy,
                                    "keep": total - noisy}

        print(f"黑名单实体 {len(report['blacklist_nodes'])} 个："
              f"{[x['name'] for x in report['blacklist_nodes']]}")
        print(f"单字实体 {len(report['one_char_nodes'])} 个："
              f"{[x['name'] for x in report['one_char_nodes']]}")
        print(f"BELONG_DISEASE 共 {total} 条，其中噪声 {noisy} 条，保留 {total - noisy} 条")

        if args.dry_run:
            print("\n--dry-run：未写入")
            Path("_clean.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            driver.close()
            return

        # —— 执行 ——
        report["deleted_blacklist"] = s.run(
            "MATCH (n) WHERE n.name IN $names DETACH DELETE n RETURN count(n) AS c",
            names=BLACKLIST).single()["c"]
        report["deleted_onechar"] = s.run(
            "MATCH (n) WHERE size(n.name) = 1 DETACH DELETE n RETURN count(n) AS c"
        ).single()["c"]
        report["deleted_edges"] = s.run(
            """
            MATCH (a:Disease)-[r:BELONG_DISEASE]->(b:Disease)
            WHERE NOT EXISTS { MATCH (b)-[:BELONG_DISEASE]->(a) }
              AND NOT EXISTS { MATCH (a)-[:HAS_SYMPTOM]->(x)<-[:HAS_SYMPTOM]-(b) }
            DELETE r RETURN count(r) AS c
            """).single()["c"]

        report["final"] = {
            "nodes": s.run("MATCH (n) RETURN count(n) AS c").single()["c"],
            "relations": s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"],
            "by_type": s.run("MATCH (n) RETURN labels(n)[0] AS t, count(*) AS c "
                             "ORDER BY c DESC").data(),
        }

    driver.close()
    print(f"\n已删除：黑名单 {report['deleted_blacklist']} 个、"
          f"单字实体 {report['deleted_onechar']} 个、"
          f"噪声关系 {report['deleted_edges']} 条")
    print(f"清洗后：{report['final']['nodes']} 节点 / {report['final']['relations']} 关系")
    Path("_clean.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()
