"""爬虫 v2：覆盖全站疾病库 + 诊断"空壳"成因 + 安全落盘。

相对 v1 的四处关键改动：

1. **入口枚举**（覆盖率 34% → 目标 100%）
   v1 只解析 `/dise/` 首页的 559 个链接；实际源站按科室/拼音分页：
     /dise/pk_{科室}_{字母}_{页}.html
     /dise/pz_{字母}_{页}.html
   本脚本枚举这些入口，实测可发现约 1600+ 个疾病。

2. **字段解析容错**（直接针对 34.8% 空壳）
   v1 只认 `<strong>标签：</strong>`；不同模板/改版会让整页解析为空。
   v2 同时支持 <strong>/<em>/<dt>/<span class> 等多种标记，并**记录页面上实际出现的标签**，
   从而区分「页面真没数据」和「我们没解析到」。

3. **空壳快照**
   解析为空的页面把 HTML 存到 data/raw/shells/，并写出标签清单，供事后分析。

4. **安全落盘**
   UTF-8 显式 + 先写 .tmp 再原子替换 + 每条记录追加 JSONL（中途崩溃不丢已爬数据）。
   —— 上次 `diseases.json` 被有损转码弄坏，就是缺了这层保护。

用法：
    python knowledge/crawl/crawl_diseases_v2.py --discover-only
    python knowledge/crawl/crawl_diseases_v2.py --limit 30 --snapshot-shells 5
    python knowledge/crawl/crawl_diseases_v2.py --names 肩周炎,胃癌,肠梗阻
    python knowledge/crawl/crawl_diseases_v2.py                 # 全量
"""
import argparse
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw"
IDS_FILE = OUT_DIR / "disease_ids_v2.json"
JSONL_FILE = OUT_DIR / "diseases_v2.jsonl"
OUT_FILE = OUT_DIR / "diseases_v2.json"
SHELL_DIR = OUT_DIR / "shells"

BASE = "https://www.youlai.cn"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

DETAIL_RE = re.compile(r'<a[^>]*href="([^"]*?/dise/(\d+)\.html)"[^>]*>(.*?)</a>', re.S)

# 页面字段 → (实体类型, 关系名)；含常见变体
FIELD_MAP = {
    "挂号科室": ("Department", "BELONG_DEPARTMENT"),
    "就诊科室": ("Department", "BELONG_DEPARTMENT"),
    "所属科室": ("Department", "BELONG_DEPARTMENT"),
    "相关症状": ("Symptom", "HAS_SYMPTOM"),
    "常见症状": ("Symptom", "HAS_SYMPTOM"),
    "症状表现": ("Symptom", "HAS_SYMPTOM"),
    "相关药品": ("Drug", "USE_DRUG"),
    "常用药品": ("Drug", "USE_DRUG"),
    "多发人群": ("Crowd", "FIT_CROWD"),
    "易感人群": ("Crowd", "FIT_CROWD"),
    "治疗方法": ("Cure", "HAS_CURE"),
    "治疗方式": ("Cure", "HAS_CURE"),
    "相关疾病": ("Disease", "BELONG_DISEASE"),
    "相关检查": ("Check", "HAS_CHECK"),
    "检查项目": ("Check", "HAS_CHECK"),
}

SKIP_VALUES = {"无", "暂无", "无相关", "未收录", "-", "", "更多", "展开"}
NAV_WORDS = {"疾病首页", "更多", "查看更多", "首页", "全部", "查看全部",
             "相关疾病", "相关症状", "相关药品", "详情", "展开"}

# 多种「标签：值」标记
LABEL_PATTERNS = [
    r"<strong>([^<：:]{2,12})[：:]</strong>\s*(<span>.*?</span>)?",
    r"<em>([^<：:]{2,12})[：:]</em>\s*(<span>.*?</span>)?",
    r"<dt>([^<：:]{2,12})[：:]?</dt>\s*<dd>(.*?)</dd>",
    r'<span[^>]*class="[^"]*(?:label|tit|name)[^"]*"[^>]*>([^<：:]{2,12})[：:]</span>\s*(<[^>]+>.*?</[^>]+>)?',
    r'<i[^>]*>([^<：:]{2,12})[：:]</i>\s*(<[^>]+>.*?</[^>]+>)?',
]
# 全体标签探测：判断"页面上到底有没有这些标签"，用于区分没数据 vs 没解析到
ANY_LABEL_RE = re.compile(r"<[a-z]+[^>]*>([\u4e00-\u9fa5]{2,8})[：:]</[a-z]+>")


def fetch(url: str, timeout: int = 25) -> str:
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(500_000).decode("utf-8", "ignore")
        except Exception as e:            # noqa: BLE001
            last = e
            time.sleep(2)
    raise last


def _strip(html: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", html)).strip()


def _split_multi(text: str) -> list:
    out = []
    for p in re.split(r"[、，,；;/\s]+", text or ""):
        p = p.strip()
        if p and p not in SKIP_VALUES and p not in NAV_WORDS and len(p) <= 20:
            out.append(p)
    return list(dict.fromkeys(out))


def write_json_atomic(path: Path, payload: dict):
    """先写 .tmp 再原子替换 —— 避免中途崩溃留下半截损坏文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---------------- ① 枚举疾病 ID ----------------

def discover(index_delay: float = 0.6, use_pinyin: bool = False) -> dict:
    """枚举全站疾病：{id: name}。"""
    found: dict[str, str] = {}

    def _scan(url: str) -> int:
        html = fetch(url)
        new = 0
        for href, did, inner in DETAIL_RE.findall(html):
            name = _strip(inner)
            if not name or len(name) > 14 or name in SKIP_VALUES:
                continue
            if did not in found:
                found[did] = name
                new += 1
        return new

    # 科室分页
    for dept in range(1, 13):
        for page in range(1, 6):
            url = f"{BASE}/dise/pk_{dept}_0_{page}.html"
            try:
                new = _scan(url)
            except Exception:
                break
            print(f"    pk_{dept}_{page}: +{new}（累计 {len(found)}）", flush=True)
            if new == 0:
                break
            time.sleep(index_delay)

    # 拼音分页（可选，交叉补充）
    if use_pinyin:
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            for page in range(1, 5):
                url = f"{BASE}/dise/pz_{letter}_{page}.html"
                try:
                    new = _scan(url)
                except Exception:
                    break
                print(f"    pz_{letter}_{page}: +{new}（累计 {len(found)}）", flush=True)
                if new == 0:
                    break
                time.sleep(index_delay)

    write_json_atomic(IDS_FILE, {
        "source": "youlai.cn/dise",
        "discoveredAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(found),
        "diseases": [{"id": k, "name": v, "url": f"{BASE}/dise/{k}.html"}
                     for k, v in found.items()],
    })
    return found


# ---------------- ② 解析详情页 ----------------

def parse_fields(html: str) -> tuple[dict, list]:
    """返回 ({规范字段: {type, relation, values}}, 页面上出现过的原始标签)。"""
    raw = {}
    for pat in LABEL_PATTERNS:
        for m in re.finditer(pat, html, re.S):
            label = m.group(1).strip()
            val_html = (m.group(2) or "") if m.lastindex and m.lastindex >= 2 else ""
            raw.setdefault(label, val_html)

    labels_seen = sorted(set(ANY_LABEL_RE.findall(html)))

    fields = {}
    for label, (etype, rel) in FIELD_MAP.items():
        if label not in raw:
            continue
        if label.startswith("相关疾病"):
            names = [_strip(x) for x in re.findall(
                r'<a[^>]*href="/dise/\d+\.html"[^>]*>(.*?)</a>', html, re.S)]
            values = [n for n in dict.fromkeys(names)
                      if n and n not in SKIP_VALUES and n not in NAV_WORDS]
        else:
            values = _split_multi(_strip(raw[label]))
        if values:
            fields[label] = {"type": etype, "relation": rel, "values": values[:20]}
    return fields, labels_seen


def crawl(items: list, delay: float, snapshot_shells: int) -> dict:
    """爬详情页，逐条追加 JSONL，返回汇总。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHELL_DIR.mkdir(parents=True, exist_ok=True)

    done_ids = set()
    if JSONL_FILE.exists():
        for line in JSONL_FILE.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(line)["id"])
            except Exception:
                continue
        print(f"  续跑：已有 {len(done_ids)} 条记录", flush=True)

    shells_saved = 0
    records, failed = [], []
    with JSONL_FILE.open("a", encoding="utf-8") as fh:
        for i, (did, name) in enumerate(items, 1):
            if did in done_ids:
                continue
            url = f"{BASE}/dise/{did}.html"
            try:
                html = fetch(url)
            except Exception as e:            # noqa: BLE001
                failed.append({"id": did, "name": name, "error": str(e)[:80]})
                print(f"  [{i}/{len(items)}] FAIL {name}", flush=True)
                time.sleep(delay)
                continue

            fields, labels_seen = parse_fields(html)
            rec = {
                "id": did,
                "name": name,
                "url": url,
                "fields": {k: v["values"] for k, v in fields.items()},
                "relations": [{"type": v["type"], "relation": v["relation"],
                               "targets": v["values"]} for v in fields.values()],
                "labelsSeen": labels_seen,        # 诊断用：页面到底有哪些标签
                "fieldCount": len(fields),
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            records.append(rec)

            if not fields and shells_saved < snapshot_shells:
                (SHELL_DIR / f"{did}.html").write_text(html, encoding="utf-8")
                shells_saved += 1
                print(f"  [{i}/{len(items)}] 空壳 {name} → 快照已存；"
                      f"页面标签: {labels_seen[:8]}", flush=True)
            else:
                print(f"  [{i}/{len(items)}] {name}: "
                      + (" ".join(f"{k}×{len(v)}" for k, v in rec["fields"].items())
                         or "（无字段）"), flush=True)

            time.sleep(delay + random.uniform(0, 0.4))

    return {"records": records, "failed": failed, "shellsSaved": shells_saved}


def report(records: list) -> dict:
    """填充率报告：每个字段有多少比例的病历抓到了。"""
    total = len(records) or 1
    empty = sum(1 for r in records if r["fieldCount"] == 0)
    per_field = {}
    for r in records:
        for k in r["fields"]:
            per_field[k] = per_field.get(k, 0) + 1
    return {
        "total": len(records),
        "emptyShell": empty,
        "emptyRate": round(empty / total * 100, 1),
        "perField": {k: {"count": v, "rate": round(v / total * 100, 1)}
                     for k, v in sorted(per_field.items(), key=lambda x: -x[1])},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="只爬前 N 个")
    ap.add_argument("--names", default="", help="定向爬指定疾病名（逗号分隔）")
    ap.add_argument("--delay", type=float, default=2.0, help="详情页限速（秒）")
    ap.add_argument("--index-delay", type=float, default=0.6, help="索引页限速（秒）")
    ap.add_argument("--use-pinyin", action="store_true", help="额外用拼音索引补充")
    ap.add_argument("--snapshot-shells", type=int, default=5, help="给几个空壳页存 HTML 快照")
    args = ap.parse_args()

    print("[1/2] 枚举疾病 ID ...", flush=True)
    if IDS_FILE.exists() and not args.discover_only:
        saved = json.loads(IDS_FILE.read_text(encoding="utf-8"))
        found = {d["id"]: d["name"] for d in saved["diseases"]}
        print(f"  复用已有清单：{len(found)} 个")
    else:
        found = discover(args.index_delay, args.use_pinyin)
        print(f"  枚举完成：{len(found)} 个疾病")

    if args.discover_only:
        return

    items = list(found.items())
    if args.names:
        wanted = [n.strip() for n in args.names.split(",") if n.strip()]
        items = [(d, n) for d, n in items if n in wanted]
        print(f"  定向爬取：{len(items)} 个 → {[n for _, n in items]}")
    elif args.limit:
        items = items[: args.limit]

    print(f"[2/2] 抓详情页（{len(items)} 个，限速 {args.delay}s）...", flush=True)
    result = crawl(items, args.delay, args.snapshot_shells)

    rep = report(result["records"])
    write_json_atomic(OUT_FILE, {
        "source": "youlai.cn/dise",
        "version": 2,
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "diseaseCount": rep["total"],
        "report": rep,
        "failed": result["failed"],
        "diseases": result["records"],
    })

    print("\n" + "=" * 56)
    print("填充率报告")
    print("=" * 56)
    print(f"  本批 {rep['total']} 个；空壳 {rep['emptyShell']} 个（{rep['emptyRate']}%）")
    for k, v in rep["perField"].items():
        print(f"    {k:<8} {v['count']:>4} 个（{v['rate']}%）")
    print(f"\n  空壳快照：{result['shellsSaved']} 个 → {SHELL_DIR}")
    print(f"  数据：{OUT_FILE}")


if __name__ == "__main__":
    main()
