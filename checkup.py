"""项目体检：一条命令看清当前状态。

用法（在仓库根目录）：
    .\\.venv\\Scripts\\python.exe checkup.py

设计原则：
  · 每项检查独立 try，任何一项失败都不影响其它项出结果；
  · 只读，不改任何东西；
  · 不依赖 Docker（容器相关只看文件是否存在）；
  · 结论分三档：🟢 健康 / 🟡 有折中 / 🔴 需处理。
"""
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

OK, WARN, BAD = "🟢", "🟡", "🔴"
findings = []          # (等级, 一句问题+建议)


def section(title):
    print(f"\n{'=' * 58}\n{title}\n{'=' * 58}")


def note(level, text):
    findings.append((level, text))


# ---------------- 代码状态 ----------------
def check_git():
    section("[1/8] 代码状态")
    try:
        log = subprocess.run(["git", "log", "--oneline", "-3"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8").stdout.strip()
        print(log or "(无提交历史)")
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8").stdout.strip()
        n_dirty = len([x for x in dirty.splitlines() if x.strip()])
        print(f"未提交文件: {n_dirty}")
        if n_dirty:
            note(WARN, f"有 {n_dirty} 个文件未提交，建议先 commit 留回滚点")

        ahead = subprocess.run(["git", "log", "--oneline", "origin/main..HEAD"],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        unpushed = len([x for x in ahead.stdout.splitlines() if x.strip()])
        if unpushed:
            note(WARN, f"有 {unpushed} 个提交未推送")
        else:
            print("与 origin/main 同步")
    except Exception as e:
        print(f"读取 git 失败: {e}")


# ---------------- 单元测试 ----------------
def check_tests():
    section("[2/8] 单元测试")
    try:
        loader = unittest.TestLoader()
        suite = loader.discover(str(ROOT / "backend" / "tests"), top_level_dir=str(ROOT / "backend"))
        buf = io.StringIO()
        result = unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
        total = result.testsRun
        failed = len(result.failures) + len(result.errors)
        print(f"共 {total} 个用例：通过 {total - failed} / 失败 {failed}")
        if failed:
            note(BAD, f"{failed} 个单元测试失败")
            for case, tb in (result.failures + result.errors)[:3]:
                print(f"  ✗ {case}")
                print("   ", tb.strip().splitlines()[-1][:160])
    except Exception as e:
        print(f"跑测试失败: {e}")


# ---------------- 接口清单 ----------------
def check_routes():
    section("[3/8] 接口")
    try:
        import main
        routes = sorted({(r.path, tuple(sorted(getattr(r, 'methods', []) or [])))
                         for r in main.app.routes if getattr(r, "path", "").startswith("/")})
        protected_prefix = ("/api/eval", "/api/kg", "/api/trace")
        pub = [p for p, _ in routes if not p.startswith(protected_prefix)]
        adm = [p for p, _ in routes if p.startswith(protected_prefix)]
        print(f"总计 {len(routes)} 个路径；管理类 {len(adm)} 个（需 X-Admin-Token）；公开 {len(pub)} 个")
        print("管理类:", ", ".join(adm))
    except Exception as e:
        print(f"加载应用失败: {e}")


# ---------------- 知识库 ----------------
def check_kb():
    section("[4/8] 知识库")
    try:
        from app.store import kg_store as k
        nodes = k.run_read("MATCH (n) RETURN count(n) AS c")[0]["c"]
        rels = k.run_read("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        iso = k.run_read("MATCH (n) WHERE NOT (n)--() RETURN count(n) AS c")[0]["c"]
        depts = k.run_read("MATCH (p:Department) RETURN count(p) AS c")[0]["c"]
        by_type = k.run_read("MATCH (n) RETURN labels(n)[0] AS t, count(*) AS c ORDER BY c DESC")
        print(f"节点 {nodes} / 关系 {rels} / 科室 {depts}")
        print("构成: " + ", ".join(f"{r['t']}={r['c']}" for r in by_type))
        rate = round(iso / nodes * 100, 1) if nodes else 0
        print(f"孤立节点 {iso}（{rate}%）")
        if rate > 20:
            note(WARN, f"孤立节点占 {rate}%，白占索引位")
    except Exception as e:
        print(f"连不上 Neo4j（容器没起？）: {e}")
        note(WARN, "Neo4j 不可达，知识库与检索相关检查被跳过")


# ---------------- 向量索引 ----------------
def check_index():
    section("[5/8] 向量索引")
    try:
        meta_path = ROOT / "knowledge" / "index" / "medical_faiss_meta.json"
        idx_path = ROOT / "knowledge" / "index" / "medical_faiss.index"
        if not meta_path.exists() or not idx_path.exists():
            print("索引文件缺失 —— 需运行 knowledge/index/build_vector_index.py")
            note(BAD, "向量索引不存在，检索会退化")
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        mb = round(idx_path.stat().st_size / 1024 / 1024, 2)
        print(f"索引条数 {len(meta)} / 文件 {mb} MB")
        try:
            from app.store import kg_store as k
            nodes = k.run_read("MATCH (n) RETURN count(n) AS c")[0]["c"]
            if nodes != len(meta):
                print(f"⚠ 索引 {len(meta)} 条 ≠ 图节点 {nodes} 个")
                note(WARN, "索引与图谱不同步，重建索引后检索指标才可信")
            else:
                print("与图谱节点数一致 ✅")
        except Exception:
            pass
    except Exception as e:
        print(f"检查失败: {e}")


# ---------------- 评估指标 ----------------
def check_eval():
    section("[6/8] 评估指标（最近一次基线）")
    try:
        p = ROOT / "eval" / "baseline.json"
        if not p.exists():
            print("无基线 —— 跑一次 `python -m app.eval --update-baseline` 生成")
            note(WARN, "缺少评估基线，CI 门禁只有绝对阈值")
            return
        b = json.loads(p.read_text(encoding="utf-8"))
        m = b.get("metrics") or {}
        print(f"基线 {b.get('taskId')}（{b.get('recordedAt')}，数据集 v{b.get('datasetVersion')}）")
        print(f"  任务成功率      {m.get('taskSuccessRate')}%")
        print(f"  Recall@5 / MRR  {m.get('recallAt5')} / {m.get('mrr')}")
        print(f"  免责/急症/拒答   {m.get('disclaimerCoverage')}% / "
              f"{m.get('emergencyRecall')}% / {m.get('refuseCompliance')}%")
        print(f"  LLM 裁判均分    {m.get('avgJudgeScore')} / 5")
        print(f"  平均耗时        {m.get('avgLatencyMs')} ms")
        if (m.get("taskSuccessRate") or 0) < 90:
            note(WARN, f"任务成功率 {m.get('taskSuccessRate')}% 偏低")
    except Exception as e:
        print(f"读取基线失败: {e}")


# ---------------- 安全与配置 ----------------
def check_security():
    section("[7/8] 安全与配置")
    try:
        from app.config import settings
        print(f"API_HOST       {settings.API_HOST}  "
              f"{'（仅本机，安全）' if settings.API_HOST.startswith('127.') else '（对局域网开放）'}")
        if not settings.API_HOST.startswith("127."):
            note(BAD, "API_HOST 不是回环地址：对话接口会暴露到局域网且无限流")

        if settings.ADMIN_TOKEN:
            print("ADMIN_TOKEN    已配置 ✅")
        else:
            print("ADMIN_TOKEN    未配置（管理接口仅本机可访问 = 默认安全）")

        print(f"证据预算       {settings.EVIDENCE_MAX_ITEMS} 条 / {settings.EVIDENCE_MAX_CHARS} 字符")
        print(f"LLM 超时/熔断  {settings.LLM_TIMEOUT}s / 连续 {settings.LLM_BREAKER_THRESHOLD} 次失败")
        print(f"结构化日志     {'开启' if settings.LOG_JSON else '关闭'}")
        if not settings.LLM_API_KEY:
            note(BAD, "LLM_API_KEY 为空，对话会直接降级")
        else:
            print("LLM_API_KEY    已配置 ✅")
    except Exception as e:
        print(f"读取配置失败: {e}")


# ---------------- 交付物 ----------------
def check_delivery():
    section("[8/8] 交付物")
    files = {
        "backend/Dockerfile": "后端镜像",
        "frontend/Dockerfile": "前端镜像",
        "frontend/nginx.conf": "Nginx 反代+限流",
        "docker-compose.yml": "全栈编排",
        "DEPLOY.md": "部署手册",
        "eval/baseline.json": "评估基线",
    }
    for rel, desc in files.items():
        print(f"  {'✅' if (ROOT / rel).exists() else '❌'} {rel:24} {desc}")
    dist = ROOT / "frontend" / "dist" / "index.html"
    print(f"  {'✅' if dist.exists() else '❌'} {'frontend/dist':24} 前端构建产物")
    print("\n  注：镜像是否真的能构建/启动，本脚本无法判断（需 Docker），"
          "请按 DEPLOY.md 第 2 节实测。")


# ---------------- 结论 ----------------
def summary():
    section("结论")
    if not findings:
        print("🟢 未发现需要处理的问题。")
    else:
        for lv in (BAD, WARN):
            items = [t for l, t in findings if l == lv]
            if items:
                print(f"\n{lv} 需处理 {len(items)} 项：")
                for t in items:
                    print(f"   · {t}")
    print("\n说明：本脚本只看本地可得的事实（git/测试/图谱/索引/基线/配置/文件）。")
    print("      容器编排是否真能跑起来，必须实际 `docker compose up` 才知道。")


if __name__ == "__main__":
    print("智慧问诊系统 · 项目体检")
    check_git()
    check_tests()
    check_routes()
    check_kb()
    check_index()
    check_eval()
    check_security()
    check_delivery()
    summary()
