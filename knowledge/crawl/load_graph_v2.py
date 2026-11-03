"""把 v2 爬取结果**增量合并**进现有图谱（不清空、可回滚）。

为什么增量而不是清空重建：
  · v2 覆盖了 v1 的全部 559 个疾病 + 1068 个全新疾病，按名字 MERGE 就能
    就地填上 296 个空壳的数据，不需要推倒重来；
  · 现有的人工/推导数据（部位症状、症状→科室、科室归一）得以保留；
  · 新写入的关系统一打 batch='v2'，出问题可精确删除，也能用
    data/raw/graph_backup_v1.json 整体恢复。

用法：
    python knowledge/crawl/load_graph_v2.py --dry-run
    python knowledge/crawl/load_graph_v2.py
    python knowledge/crawl/load_graph_v2.py --revert
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase                     # noqa: E402

from app.config import settings                     # noqa: E402

SRC = ROOT / "data" / "raw" / "diseases_v2.json"

# 标签/关系白名单（防脏数据写入任意标签）
ALLOWED_LABELS = {"Disease", "Symptom", "Drug", "Check", "Department",
                  "Crowd", "Cure", "Cause", "Taboo"}
ALLOWED_RELS = {"BELONG_DEPARTMENT", "HAS_SYMPTOM", "USE_DRUG", "FIT_CROWD",
                "HAS_CURE", "BELONG_DISEASE", "HAS_CHECK", "HAS_CAUSE",
                "HAS_TABOO"}

MAX_TARGETS = 20       # 单条关系最多挂几个目标
MIN_NAME, MAX_NAME = 2, 20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    with driver.session() as s:
        if args.revert:
            n = s.run("MATCH ()-[r]->() WHERE r.batch = 'v2' DELETE r "
                      "RETURN count(r) AS c").single()["c"]
            print(f"已回滚：删除 v2 关系 {n} 条（节点保留，可能变空壳）")
            driver.close()
            return

        data = json.loads(SRC.read_text(encoding="utf-8"))
        diseases = data["diseases"]
        if args.limit:
            diseases = diseases[: args.limit]
        print(f"源数据：{len(diseases)} 个疾病（文件记录 {data['diseaseCount']}）")

        # ---- 规划：统计将写入的关系 ----
        rel_counter = Counter()
        node_names = {"Disease": set()}
        new_rels = []          # (disease, rel, label, target)
        skipped = Counter()

        for d in diseases:
            name = (d.get("name") or "").strip()
            if not (MIN_NAME <= len(name) <= MAX_NAME):
                skipped["名称不合法"] += 1
                continue
            node_names["Disease"].add(name)
            for r in d.get("relations") or []:
                rel, label = r.get("relation"), r.get("type")
                if rel not in ALLOWED_RELS or label not in ALLOWED_LABELS:
                    skipped[f"非白名单 {rel}/{label}"] += 1
                    continue
                for t in (r.get("targets") or [])[:MAX_TARGETS]:
                    t = (t or "").strip()
                    if not (MIN_NAME <= len(t) <= MAX_NAME) or t == name:
                        skipped["目标名不合法"] += 1
                        continue
                    rel_counter[rel] += 1
                    node_names.setdefault(label, set()).add(t)
                    new_rels.append((name, rel, label, t))

        print(f"\n将写入关系 {len(new_rels)} 条，按类型：")
        for rel, n in rel_counter.most_common():
            print(f"  {rel:<20} {n}")
        print(f"\n涉及节点：")
        for label, names in sorted(node_names.items()):
            print(f"  {label:<12} {len(names)}")
        if skipped:
            print(f"\n跳过：{dict(skipped)}")

        if args.dry_run:
            print("\n--dry-run：未写入")
            driver.close()
            return

        # ---- 写入：节点按名字 MERGE，关系打 batch 标记 ----
        # 19k+ 关系逐条 MERGE 太慢，按 (关系, 标签) 分组用 UNWIND 批量写
        from collections import defaultdict

        groups = defaultdict(list)
        for name, rel, label, target in new_rels:
            groups[(rel, label)].append({"d": name, "t": target})

        written = 0
        with driver.session() as tx:
            tx.run("UNWIND $names AS n MERGE (d:Disease {name: n})",
                   names=list(node_names.get("Disease", ())))

            for (rel, label), rows in groups.items():
                for i in range(0, len(rows), 500):
                    chunk = rows[i:i + 500]
                    tx.run(
                        f"""
                        UNWIND $rows AS row
                        MATCH (d:Disease {{name: row.d}})
                        MERGE (t:{label} {{name: row.t}})
                        MERGE (d)-[r:{rel}]->(t)
                        SET r.batch = 'v2', r.source = 'youlai_v2'
                        """,
                        rows=chunk,
                    )
                    written += len(chunk)
                print(f"  {rel:<20} {len(rows)} 条 ✅", flush=True)

        total_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        total_rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        shells = s.run("MATCH (n) WHERE NOT (n)--() RETURN count(n) AS c").single()["c"]
    driver.close()

    print(f"\n已写入 {written} 条关系")
    print(f"当前图谱：{total_nodes} 节点 / {total_rels} 关系 / 孤立节点 {shells}")
    print("回滚：python knowledge/crawl/load_graph_v2.py --revert")


if __name__ == "__main__":
    main()
