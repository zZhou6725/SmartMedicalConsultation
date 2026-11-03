"""从「症状—疾病—科室」共现推导 症状→科室 直连边。

为什么需要：
  用户问「我肩膀痛」时 symptoms / department 都是空。原因之一是**症状到科室没有直连**——
  图谱里只有 疾病→科室（BELONG_DEPARTMENT 560 条），一旦疾病是空壳（34.8% 的疾病
  没有任何关系），这条路就断了。而症状→科室是用户在症状类提问里最想要的信息。

做法：统计"某个症状出现在哪些疾病上、这些疾病又属于什么科室"，取众数建边，
并标注来源与支持度，便于审计与一键回滚。

安全设计：
  · 只建 `derived: true` 的边，`--revert` 可一次性全删；
  · 支持度阈值 + 占比阈值双重过滤，避免个例噪声；
  · 每个症状最多保留 2 个科室；
  · 不覆盖已有的人工/爬取边。

用法：
    python knowledge/crawl/derive_symptom_department.py --dry-run
    python knowledge/crawl/derive_symptom_department.py
    python knowledge/crawl/derive_symptom_department.py --revert
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

MIN_SUPPORT = 2          # 至少被 2 个疾病支持，防止个例噪声
MIN_SHARE = 0.25         # 次要科室至少占该症状的 25%
MAX_DEPT_PER_SYMPTOM = 2


def fetch_candidates(session) -> dict:
    """返回 {症状: [(科室, 支持数, 总支持)]}（已按支持数倒序）。"""
    rows = session.run(
        """
        MATCH (s:Symptom)<-[:HAS_SYMPTOM]-(d:Disease)-[:BELONG_DEPARTMENT]->(p:Department)
        WITH s, p, count(DISTINCT d) AS support
        WITH s, collect({dept: p.name, support: support}) AS pairs,
             sum(support) AS total
        RETURN s.name AS symptom, pairs, total
        ORDER BY total DESC
        """
    ).data()

    out = {}
    for r in rows:
        symptom = (r["symptom"] or "").strip()
        if not symptom:
            continue
        pairs = sorted(r["pairs"], key=lambda x: -x["support"])
        total = r["total"] or sum(p["support"] for p in pairs) or 1
        kept = []
        for p in pairs[:MAX_DEPT_PER_SYMPTOM]:
            share = p["support"] / total
            if p["support"] >= MIN_SUPPORT and (not kept or share >= MIN_SHARE):
                kept.append((p["dept"], p["support"], round(share, 3)))
        if kept:
            out[symptom] = kept
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只出报告，不写库")
    ap.add_argument("--revert", action="store_true", help="删除所有 derived 边（回滚）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个症状（调试用）")
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    with driver.session() as s:
        if args.revert:
            n = s.run(
                "MATCH ()-[r:BELONG_DEPARTMENT]->() WHERE r.derived = true "
                "DELETE r RETURN count(r) AS c"
            ).single()["c"]
            print(f"已回滚：删除 {n} 条 derived 边")
            left = s.run(
                "MATCH (:Symptom)-[r:BELONG_DEPARTMENT]->(:Department) RETURN count(r) AS c"
            ).single()["c"]
            print(f"剩余 症状→科室 边：{left} 条")
            driver.close()
            return

        candidates = fetch_candidates(s)
        if args.limit:
            candidates = dict(list(candidates.items())[: args.limit])

        total_edges = sum(len(v) for v in candidates.values())
        all_symptoms = s.run("MATCH (s:Symptom) RETURN count(s) AS c").single()["c"]
        print(f"症状总数 {all_symptoms}；可推导出科室的症状 {len(candidates)} 个；"
              f"将新增 {total_edges} 条 症状→科室 边")
        print(f"阈值：支持数 ≥ {MIN_SUPPORT}，次要科室占比 ≥ {MIN_SHARE:.0%}，"
              f"每症状最多 {MAX_DEPT_PER_SYMPTOM} 个科室")

        # 冲突/歧义：同一症状有 ≥2 个科室且占比都不低
        ambiguous = {k: v for k, v in candidates.items() if len(v) > 1}
        print(f"\n有 2 个科室候选（歧义较大）的症状：{len(ambiguous)} 个，样本：")
        for k, v in list(ambiguous.items())[:8]:
            print(f"  {k:<10} → " + ", ".join(f"{d}({sup},{sh:.0%})" for d, sup, sh in v))

        print(f"\n单科室、支持度最高的样本：")
        single = [(k, v[0]) for k, v in candidates.items() if len(v) == 1][:10]
        for k, (d, sup, sh) in single:
            print(f"  {k:<10} → {d}（{sup} 个疾病支持）")

        # 用户关心的那几个
        print("\n关键抽查（肩部 / 常见词）：")
        for name in ["肩痛", "耸肩", "疼痛", "关节痛", "头痛", "咳嗽", "腹痛"]:
            got = candidates.get(name)
            print(f"  {name:<8} → " + (", ".join(f"{d}({s})" for d, s, _ in got)
                                       if got else "（无可推导结果）"))

        report = {
            "totalSymptoms": all_symptoms,
            "derivable": len(candidates),
            "edges": total_edges,
            "thresholds": {"minSupport": MIN_SUPPORT, "minShare": MIN_SHARE,
                           "maxDeptPerSymptom": MAX_DEPT_PER_SYMPTOM},
            "ambiguousCount": len(ambiguous),
            "detail": {k: v for k, v in candidates.items()},
        }
        Path("_derive_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        if args.dry_run:
            print("\n--dry-run：未写入（明细见 _derive_report.json）")
            driver.close()
            return

        created = 0
        with driver.session() as tx:
            for symptom, depts in candidates.items():
                for dept, support, share in depts:
                    tx.run(
                        """
                        MATCH (s:Symptom {name: $s}), (p:Department {name: $d})
                        WHERE NOT EXISTS {
                            MATCH (s)-[e:BELONG_DEPARTMENT]->(p) WHERE e.derived IS NULL
                        }
                        MERGE (s)-[r:BELONG_DEPARTMENT]->(p)
                        SET r.derived = true,
                            r.support = $support,
                            r.share = $share,
                            r.source = 'cooccurrence'
                        """,
                        s=symptom, d=dept, support=support, share=share,
                    )
                    created += 1

        final = s.run(
            "MATCH (:Symptom)-[r:BELONG_DEPARTMENT]->(:Department) RETURN count(r) AS c"
        ).single()["c"]
    driver.close()

    print(f"\n已写入 {created} 条（含已存在的幂等跳过）；"
          f"当前 症状→科室 边共 {final} 条")
    print("回滚命令：python knowledge/crawl/derive_symptom_department.py --revert")


if __name__ == "__main__":
    main()
