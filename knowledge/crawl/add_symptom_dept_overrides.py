"""补一批「常见症状 → 首诊科室」的人工归属（curated），纠正统计推导的偏差。

为什么需要：
  症状→科室是靠「疾病中转的众数」统计出来的，数据一多就会偏。
  实测：头晕在 v2 数据里被推到「神经外科」（support 仅 9、占比 25%），
  而正确答案是神经内科 —— 这类常识性归属不该交给众数投票。

做法：一小张可审计的表，打 curated=true、support=999（保证在排序中胜出）。
只覆盖最常见、归属无争议的症状；有争议的一律不加。

用法：
    python knowledge/crawl/add_symptom_dept_overrides.py --dry-run
    python knowledge/crawl/add_symptom_dept_overrides.py
    python knowledge/crawl/add_symptom_dept_overrides.py --revert
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase                     # noqa: E402

from app.config import settings                     # noqa: E402

# 症状 → 首诊科室（归属无争议的常见症状）
OVERRIDES = {
    "头晕": "神经内科",
    "眩晕": "神经内科",
    "头痛": "神经内科",
    "偏头痛": "神经内科",
    "发热": "普通内科",
    "咳嗽": "呼吸内科",
    "咳痰": "呼吸内科",
    "胸闷": "心血管内科",
    "心悸": "心血管内科",
    "胸痛": "心血管内科",
    "腹痛": "消化内科",
    "恶心": "消化内科",
    "呕吐": "消化内科",
    "腹泻": "消化内科",
    "便秘": "消化内科",
    "皮疹": "皮肤科",
    "关节痛": "风湿免疫科",
    "贫血": "血液内科",
    "水肿": "肾内科",
    "尿频": "泌尿外科",
}

CURATED_SUPPORT = 999      # 保证在 _derive 的排序里胜过统计推导


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    with driver.session() as s:
        if args.revert:
            n = s.run(
                "MATCH (:Symptom)-[r:BELONG_DEPARTMENT {source: 'override'}]->(:Department) "
                "DELETE r RETURN count(r) AS c").single()["c"]
            print(f"已回滚 {n} 条人工归属边")
            driver.close()
            return

        plan, missing = [], []
        for sym, dept in OVERRIDES.items():
            sym_ok = s.run("MATCH (a:Symptom {name: $n}) RETURN count(a) AS c",
                           n=sym).single()["c"] > 0
            dept_ok = s.run("MATCH (p:Department {name: $d}) RETURN count(p) AS c",
                            d=dept).single()["c"] > 0
            if sym_ok and dept_ok:
                plan.append((sym, dept))
            else:
                missing.append(f"{sym}→{dept}"
                               f"{'（无此症状）' if not sym_ok else ''}"
                               f"{'（无此科室）' if not dept_ok else ''}")

        print(f"可写入 {len(plan)} 条人工归属：")
        for sym, dept in plan:
            print(f"  {sym:<8} → {dept}")
        if missing:
            print(f"\n跳过 {len(missing)} 条（节点不存在）：{'、'.join(missing)}")

        if args.dry_run:
            print("\n--dry-run：未写入")
            driver.close()
            return

        with driver.session() as tx:
            for sym, dept in plan:
                tx.run(
                    """
                    MATCH (a:Symptom {name: $s}), (p:Department {name: $d})
                    MERGE (a)-[r:BELONG_DEPARTMENT]->(p)
                    SET r.curated = true, r.source = 'override',
                        r.support = $sup, r.share = 1.0
                    """, s=sym, d=dept, sup=CURATED_SUPPORT)

        total = s.run(
            "MATCH (:Symptom)-[r:BELONG_DEPARTMENT]->(:Department) RETURN count(r) AS c"
        ).single()["c"]
    driver.close()
    print(f"\n已写入 {len(plan)} 条；当前 症状→科室 边共 {total} 条")
    print("回滚：python knowledge/crawl/add_symptom_dept_overrides.py --revert")


if __name__ == "__main__":
    main()
