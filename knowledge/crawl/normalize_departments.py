"""科室名归一化：修掉「神经内科中医神经内科」这类粘连名。

成因：爬虫的 _strip() 把页面里的空白全删了，于是「神经内科　中医神经内科」
被粘成一个实体。本脚本对已有图谱做一次性修正（可重复执行）：

  1. 用已知科室词表做前缀切分，一个粘连名拆成多个科室；
  2. 中医X科 → X科（中医神经内科归到神经内科）；
  3. 康复医学科/遗传咨询科/中西医结合科这类附加科直接丢弃（不参与导诊）；
  4. 重指向 BELONG_DEPARTMENT 边，并删除不再被引用的脏科室节点。

用法：
    python knowledge/crawl/normalize_departments.py --dry-run
    python knowledge/crawl/normalize_departments.py
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase                     # noqa: E402

from app.config import settings                     # noqa: E402

# 认可的规范科室（按长度倒序匹配，避免「肾内科」抢先吃掉「风湿免疫科」这类情况）
CANON = sorted([
    "神经内科", "心血管内科", "消化内科", "内分泌科", "血液内科",
    "呼吸内科", "感染内科", "肾内科", "风湿免疫科", "普通内科",
    "过敏反应科", "老年病科",
], key=len, reverse=True)

# 已知但不需要单独成节点的附加科（出现即丢弃）
DROP_PARTS = ["康复医学科", "遗传咨询科", "中西医结合科", "脑血管病康复",
              "中医神经内科", "中医肾病科", "中医免疫内科", "中医呼吸科",
              "中医感染内科", "中医内分泌科", "中医血液科"]


def normalize(name: str) -> list:
    """把一个科室名拆成规范科室列表。"""
    out = []
    rest = name
    for part in DROP_PARTS:
        rest = rest.replace(part, "|")
    # 先按丢弃词切开，再按规范词贪心切分
    for chunk in rest.split("|"):
        i = 0
        while i < len(chunk):
            for canon in CANON:
                if chunk.startswith(canon, i):
                    out.append(canon)
                    i += len(canon)
                    break
            else:
                i += 1
    return list(dict.fromkeys(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    with driver.session() as s:
        rows = s.run(
            "MATCH (d:Disease)-[:BELONG_DEPARTMENT]->(p:Department) "
            "RETURN p.name AS dept, count(d) AS c ORDER BY c DESC").data()

    plan = defaultdict(list)          # 旧名 -> 新名列表
    for r in rows:
        old = r["dept"] or ""
        new = normalize(old)
        if new != [old]:
            plan[old] = new

    print(f"现有科室 {len(rows)} 个，需要归一化 {len(plan)} 个：")
    for old, new in plan.items():
        print(f"  {old:28} → {new or '（丢弃）'}")

    if args.dry_run:
        print("\n--dry-run：未写入")
        driver.close()
        return

    moved = 0
    with driver.session() as s:
        for old, news in plan.items():
            if not news:                       # 没有可归的目标，保留原名不动
                continue
            for new in news:
                s.run(
                    """
                    MATCH (d:Disease)-[:BELONG_DEPARTMENT]->(p:Department {name: $old})
                    MERGE (q:Department {name: $new})
                    MERGE (d)-[:BELONG_DEPARTMENT]->(q)
                    """,
                    old=old, new=new,
                )
            # 切断旧边（新边已建好）
            s.run(
                "MATCH (d:Disease)-[r:BELONG_DEPARTMENT]->(p:Department {name: $old}) DELETE r",
                old=old,
            )
            moved += 1

        # 删除不再被引用的脏科室节点
        s.run("MATCH (p:Department) WHERE NOT (p)<-[:BELONG_DEPARTMENT]-() DELETE p")

        counts = s.run(
            "MATCH (d:Disease)-[:BELONG_DEPARTMENT]->(p:Department) "
            "RETURN p.name AS dept, count(d) AS c ORDER BY c DESC").data()

    driver.close()
    print(f"\n已归一化 {moved} 个旧科室")
    print(f"当前科室 {len(counts)} 个：")
    for r in counts:
        print(f"  {r['dept']:14} {r['c']}")


if __name__ == "__main__":
    main()
