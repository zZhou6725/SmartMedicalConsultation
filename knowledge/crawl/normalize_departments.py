"""科室名归一化 v2：只拆「粘连名」，绝不丢弃未知科室。

背景（v1 的严重 bug）：
  v1 的 CANON 白名单只有原来那 12 个内科科室，一旦遇到新数据里的
  皮肤科 / 妇科 / 神经外科 / 产科 / 肿瘤内科 … 会把它们全部判为「丢弃」——
  v2 入库后科室从 12 涨到 97，直接跑 v1 会把整套外科/妇产/儿科科室删光。

v2 的规则（保守，只做拆分，不删科室）：
  1. 若某科室名以另一个已知科室名为前缀（如「神经内科中医神经内科」以「神经内科」开头）
     → 视为粘连名，取最长前缀，剩余部分继续尝试；
  2. 剩余部分若以「中医」开头，剥掉再试（中医X科 → X科）；
  3. 拆不出任何已知科室 → **原样保留**（宁可留脏名，也不丢科室）；
  4. 只有搬空后不再被引用的节点才删除。

用法：
    python knowledge/crawl/normalize_departments.py --dry-run
    python knowledge/crawl/normalize_departments.py
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase                     # noqa: E402

from app.config import settings                     # noqa: E402


def build_splitter(names: set):
    """返回 split(name) -> 拆出的科室列表（拆不出来就返回 [name]）。"""
    ordered = sorted(names, key=len, reverse=True)   # 长名优先，避免误切

    def split(name: str) -> list:
        parts, rest, changed, guard = [], name, False, 0
        while rest and guard < 6:
            guard += 1
            matched = None
            for cand in ordered:
                if cand != name and len(cand) >= 3 and rest.startswith(cand):
                    matched = cand
                    break
            if matched:
                parts.append(matched)
                rest = rest[len(matched):]
                changed = True
                continue
            if rest.startswith("中医"):          # 中医X科 → 继续尝试 X科
                rest = rest[2:]
                changed = True
                continue
            break
        if not parts:
            return [name]
        return list(dict.fromkeys(parts)) if changed else [name]

    return split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    with driver.session() as s:
        rows = s.run(
            "MATCH (p:Department) "
            "RETURN p.name AS name, size([(d:Disease)-[:BELONG_DEPARTMENT]->(p) | d]) AS n "
            "ORDER BY name").data()
        names = {r["name"] for r in rows if r["name"]}
        split = build_splitter(names)

        plan = {}
        for r in rows:
            new = split(r["name"])
            if new != [r["name"]]:
                plan[r["name"]] = {"to": new, "diseases": r["n"]}

        total_move = sum(len(v["to"]) for v in plan.values())
        print(f"科室总数 {len(names)}，需拆分 {len(plan)} 个，"
              f"将产生 {total_move} 条重指向")
        print(f"{'旧名':<24}{'拆分结果':<32}疾病数")
        for old, v in sorted(plan.items(), key=lambda x: -x[1]["diseases"]):
            print(f"{old:<24}{' + '.join(v['to']):<32}{v['diseases']}")

        if args.dry_run:
            print("\n--dry-run：未写入（提醒：v1 会把未在白名单里的科室全部丢弃）")
            driver.close()
            return

        moved = 0
        with driver.session() as tx:
            for old, v in plan.items():
                for new in v["to"]:
                    tx.run(
                        """
                        MATCH (d:Disease)-[:BELONG_DEPARTMENT]->(p:Department {name: $old})
                        MERGE (q:Department {name: $new})
                        MERGE (d)-[:BELONG_DEPARTMENT]->(q)
                        """, old=old, new=new)
                tx.run(
                    "MATCH (d:Disease)-[r:BELONG_DEPARTMENT]->(p:Department {name: $old}) "
                    "DELETE r", old=old)
                moved += 1

            removed = tx.run(
                "MATCH (p:Department) WHERE NOT (p)<-[:BELONG_DEPARTMENT]-() "
                "DETACH DELETE p RETURN count(p) AS c").single()["c"]
            left = tx.run("MATCH (p:Department) RETURN count(p) AS c").single()["c"]

    driver.close()
    print(f"\n已处理 {moved} 个粘连科室；删除无引用科室 {removed} 个；"
          f"当前科室 {left} 个")


if __name__ == "__main__":
    main()
