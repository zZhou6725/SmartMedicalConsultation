"""补建「部位 + 痛」症状实体，并接上科室与常见疾病。

背景（真实 badcase）：
  用户问「我现在肩膀有点痛」→ 症状标签空、推荐科室空、上下文只有 108 字符。
  根因：图谱里没有"肩痛"这个症状实体（肩相关只有"耸肩"），
        而"肩周炎/肩关节损伤"是空壳节点（0 条关系），科室来源整条断掉。

另一个发现：现有 12 个科室**全是内科系**（神经/心血管/消化/内分泌/血液/呼吸/
感染/肾/风湿免疫/普通/过敏/老年病），外科系统整块缺失，"骨科"根本不存在。
所以本脚本连科室节点一起补，并标记 curated 以便审计与回滚。

**刻意不做**：不给 299 个空壳疾病自动补症状/检查/用药 —— 那是猜，宁可留空。

用法：
    python knowledge/crawl/add_part_symptoms.py --dry-run
    python knowledge/crawl/add_part_symptoms.py
    python knowledge/crawl/add_part_symptoms.py --revert
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase                     # noqa: E402

from app.config import settings                     # noqa: E402

# (症状名, 首诊科室, 可关联疾病)
PARTS = [
    ("肩痛", "骨科", ["肩周炎", "肩关节损伤"]),
    ("膝痛", "骨科", ["膝关节骨关节炎"]),
    ("颈痛", "骨科", ["颈椎病"]),
    ("腰痛", "骨科", ["腰椎间盘突出症", "腰肌劳损"]),
    ("踝痛", "骨科", ["踝关节扭伤"]),
    ("肘痛", "骨科", ["网球肘"]),
    ("腕痛", "骨科", ["腕管综合征"]),
    ("髋痛", "骨科", ["髋关节骨关节炎"]),
]

# 需要补齐的科室（原数据只有内科系）
NEW_DEPTS = {
    "骨科": "骨科：诊治骨折、关节与脊柱疾病、运动损伤、慢性疼痛（如肩周炎、"
            "椎间盘突出、关节骨关节炎）等；部位性疼痛与外伤后疼痛通常首诊骨科。",
}

DESC = "{name}：{part}部位疼痛。常见于{examples}等；首诊科室一般为骨科，" \
       "如伴外伤、明显肿胀、活动受限或持续加重，应尽快就医。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    with driver.session() as s:
        if args.revert:
            e1 = s.run("MATCH ()-[r]->() WHERE r.curated = true DELETE r "
                       "RETURN count(r) AS c").single()["c"]
            n = s.run("MATCH (n) WHERE n.curated = true DETACH DELETE n "
                      "RETURN count(n) AS c").single()["c"]
            print(f"已回滚：关系 {e1} 条、节点 {n} 个")
            driver.close()
            return

        # ---------- 规划 ----------
        dept_status = {}
        for dept in NEW_DEPTS:
            cnt = s.run("MATCH (p:Department {name: $d}) RETURN count(p) AS c",
                        d=dept).single()["c"]
            dept_status[dept] = cnt > 0

        plan = []
        for name, dept, diseases in PARTS:
            existing = s.run(
                "MATCH (n {name: $n}) RETURN labels(n)[0] AS t LIMIT 1",
                n=name).data()
            existing_type = existing[0]["t"] if existing else None
            hit = [d for d in diseases
                   if s.run("MATCH (d:Disease {name: $n}) RETURN count(d) AS c",
                            n=d).single()["c"] > 0]
            plan.append((name, dept, existing_type, hit))

        print(f"{'症状':<6}{'科室':<6}{'当前状态':<22}{'可关联疾病'}")
        for name, dept, etype, hit in plan:
            state = "不存在 → 新建 Symptom" if etype is None else f"已存在（{etype}）"
            print(f"{name:<6}{dept:<6}{state:<22}{hit or '（图谱无此病，仅建症状+科室）'}")

        print("\n需要补建的科室：" +
              (", ".join(f"{d}（缺）" for d, ok in dept_status.items() if not ok) or "无"))
        n_new_sym = sum(1 for _, _, t, _ in plan if t is None)
        n_new_dept = sum(1 for ok in dept_status.values() if not ok)
        n_sym_edges = sum(len(h) for _, _, _, h in plan)
        print(f"小结：新建症状 {n_new_sym} 个、科室 {n_new_dept} 个；"
              f"补 HAS_SYMPTOM {n_sym_edges} 条；补 症状→科室 {len(plan)} 条")

        if args.dry_run:
            print("\n--dry-run：未写入")
            driver.close()
            return

        # ---------- 写入 ----------
        created_dept, created_sym_node, created_rel = 0, 0, 0
        with driver.session() as tx:
            for dept, ok in dept_status.items():
                if not ok:
                    tx.run(
                        "CREATE (p:Department {name: $d, curated: true}) "
                        "SET p.desc = $desc", d=dept, desc=NEW_DEPTS[dept])
                    created_dept += 1

            for name, dept, existing_type, diseases in plan:
                if existing_type is None:
                    tx.run(
                        "CREATE (s:Symptom {name: $n, curated: true}) SET s.desc = $desc",
                        n=name,
                        desc=DESC.format(name=name, part=name[0],
                                         examples="、".join(diseases) or "多种原因"))
                    created_sym_node += 1
                if existing_type in (None, "Symptom"):
                    tx.run(
                        """
                        MATCH (s:Symptom {name: $s}), (p:Department {name: $d})
                        MERGE (s)-[r:BELONG_DEPARTMENT]->(p)
                        SET r.curated = true, r.source = 'part_rule'
                        """, s=name, d=dept)
                    created_rel += 1
                for d in diseases:
                    tx.run(
                        """
                        MATCH (d:Disease {name: $d}), (s:Symptom {name: $s})
                        MERGE (d)-[r:HAS_SYMPTOM]->(s)
                        SET r.curated = true, r.source = 'part_rule'
                        """, d=d, s=name)
                    created_rel += 1

        print(f"\n已写入：科室 {created_dept}、症状节点 {created_sym_node}、"
              f"关系 {created_rel}")
        print("回滚：python knowledge/crawl/add_part_symptoms.py --revert")
    driver.close()


if __name__ == "__main__":
    main()
