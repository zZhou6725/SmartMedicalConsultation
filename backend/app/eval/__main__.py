"""命令行入口：跑一次评估并输出报告。

用法（在 backend 目录下）：
    python -m app.eval                     # 全量 53 条 + LLM 裁判（约数分钟）
    python -m app.eval --limit 8            # 只跑前 8 条，快速冒烟
    python -m app.eval --no-judge           # 关掉 LLM 裁判，只看确定性指标
    python -m app.eval --no-persist         # 不写 eval_record 表
"""
import argparse
import json
import sys

from app.eval import runner


def main():
    ap = argparse.ArgumentParser(description="智慧问诊系统自动化评估")
    ap.add_argument("--dataset", default="golden53", help="金标数据集ID")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    ap.add_argument("--no-judge", action="store_true", help="关闭 LLM 裁判")
    ap.add_argument("--no-persist", action="store_true", help="不写 eval_record 表")
    ap.add_argument("--update-baseline", action="store_true",
                    help="把本次结果记为基线（供下次做相对基线比对）")
    ap.add_argument("--json", action="store_true", help="标准输出打印完整结果 JSON")
    args = ap.parse_args()

    def progress(i, n, item):
        # 控制台只打 ASCII，避免 Windows 编码问题；中文详见报告文件
        print(f"[{i}/{n}] pass={item['pass']} score={item['score']} "
              f"intent={item['intent']} latency={item['latencyMs']}ms",
              file=sys.stderr, flush=True)

    summary = runner.run_eval(
        dataset_id=args.dataset,
        limit=args.limit,
        use_judge=not args.no_judge,
        persist=not args.no_persist,
        update_baseline=args.update_baseline,
        progress=progress,
    )

    m, g = summary["metrics"], summary["gate"]
    print("=" * 60)
    print(f"taskId            : {summary['taskId']}")
    print(f"total/pass/fail   : {summary['total']} / {summary['passCount']} / {summary['failCount']}")
    print(f"passRate          : {m['taskSuccessRate']}%")
    print(f"disclaimerCoverage: {m['disclaimerCoverage']}%")
    print(f"emergencyRecall   : {m['emergencyRecall']}%")
    print(f"refuseCompliance  : {m['refuseCompliance']}%")
    print(f"keywordHitRate    : {m['keywordHitRate']}%")
    print(f"recallAt5 / mrr   : {m['recallAt5']} / {m['mrr']}")
    print(f"toolCallErrorRate : {m['toolCallErrorRate']}%")
    print(f"avgLatencyMs      : {m['avgLatencyMs']}")
    print(f"gate              : {'PASSED' if g['passed'] else 'BLOCKED ' + str(g['blockers'])}")
    print(f"report            : {summary.get('reportPath')}")

    bl = summary.get("baseline") or {}
    if bl.get("available"):
        print(f"baseline          : {bl.get('baselineTaskId')} ({bl.get('recordedAt')})")
        for key, v in (bl.get("deltas") or {}).items():
            flag = "REGRESSED" if v["regressed"] else "ok"
            print(f"  {key:18} {v['baseline']} -> {v['current']} "
                  f"({v['delta']:+}) tol={v['tolerance']} {flag}")
    else:
        print("baseline          : none (use --update-baseline to record)")
    if summary.get("baselinePath"):
        print(f"baseline saved    : {summary['baselinePath']}")

    if args.json:
        print(json.dumps({k: v for k, v in summary.items() if k != "items"},
                         ensure_ascii=False, indent=2))

    return 0 if g["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
