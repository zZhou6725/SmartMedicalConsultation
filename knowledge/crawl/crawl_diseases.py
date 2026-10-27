"""从有来医生疾病库抓取结构化疾病数据，产出知识图谱源数据。

来源：https://www.youlai.cn/dise/
  robots.txt 仅禁止 /jingbian/uarticle/、/sjapp*、/lhcp*，疾病页允许抓取。

策略：
  · 只取页面里已结构化的字段（挂号科室 / 相关症状 / 相关药品 …），
    不抓正文自由文本 —— 精度高、无需 LLM 抽取、可复核；
  · 限速 1.5 秒/请求，失败重试 2 次；结果落盘，中断可续跑；
  · 产出 data/raw/diseases.json（data/raw/ 已在 .gitignore 中）。

用法：
    python knowledge/crawl/crawl_diseases.py --limit 8      # 小样验证
    python knowledge/crawl/crawl_diseases.py                # 全量 559 个
"""
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw"
OUT_FILE = OUT_DIR / "diseases.json"

INDEX_URL = "https://www.youlai.cn/dise/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
DELAY = 1.5          # 限速：每秒不超过 1 个请求
RETRY = 2

# 页面字段 → (实体类型, 关系名)
FIELD_MAP = {
    "挂号科室": ("Department", "BELONG_DEPARTMENT"),
    "相关症状": ("Symptom", "HAS_SYMPTOM"),
    "相关药品": ("Drug", "USE_DRUG"),
    "多发人群": ("Crowd", "FIT_CROWD"),
    "治疗方法": ("Cure", "HAS_CURE"),
    "相关疾病": ("Disease", "BELONG_DISEASE"),
    "相关检查": ("Check", "HAS_CHECK"),
}

# 无意义的占位值
SKIP_VALUES = {"无", "暂无", "无相关", "未收录", "-", ""}

# 页面导航/按钮文案，不能当成实体
NAV_WORDS = {"疾病首页", "更多", "查看更多", "首页", "全部", "查看全部",
             "相关疾病", "相关症状", "相关药品", "详情", "展开"}


def fetch(url: str, limit: int = 400_000) -> str:
    last = None
    for _ in range(RETRY + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read(limit).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2)
    raise last


def _strip(html: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", html)).strip()


def _split_multi(text: str) -> list:
    parts = re.split(r"[、，,；;/\s]+", text or "")
    out = []
    for p in parts:
        p = p.strip()
        if p and p not in SKIP_VALUES and p not in NAV_WORDS and len(p) <= 20:
            out.append(p)
    return list(dict.fromkeys(out))


def parse_fields(html: str) -> dict:
    """抽取页面里的「<strong>标签：</strong><span>值</span>」结构化字段。"""
    raw = {}
    for m in re.finditer(
            r"<strong>([^<：]{2,12})[：:]</strong>\s*(<span>.*?</span>)?", html, re.S):
        label = m.group(1).strip()
        val_html = m.group(2) or ""
        if label in raw:
            continue
        raw[label] = val_html

    fields = {}
    for label, (etype, rel) in FIELD_MAP.items():
        if label not in raw:
            continue

        # 「相关疾病」优先取链接锚文本（更干净）
        if label == "相关疾病":
            names = [_strip(x) for x in re.findall(
                r'<a[^>]*href="/dise/\d+\.html"[^>]*>(.*?)</a>', html, re.S)]
            values = [n for n in dict.fromkeys(names)
                      if n and n not in SKIP_VALUES and n not in NAV_WORDS]
        else:
            values = _split_multi(_strip(raw[label]))

        if values:
            fields[label] = {"type": etype, "relation": rel, "values": values[:20]}
    return fields


def crawl_index() -> dict:
    """抓疾病库索引，返回 {url: 疾病名}。"""
    html = fetch(INDEX_URL)
    anchors = re.findall(r'<a[^>]*href="([^"]*?/dise/\d+\.html)"[^>]*>(.*?)</a>', html, re.S)
    out = {}
    for href, inner in anchors:
        name = _strip(inner)
        if not name or len(name) > 12 or name in SKIP_VALUES:
            continue
        url = href if href.startswith("http") else "https://www.youlai.cn" + href
        out.setdefault(url, name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 个疾病（0=全量）")
    ap.add_argument("--resume", action="store_true", help="跳过已抓过的疾病")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[1/2] 抓取疾病库索引 ...", flush=True)
    index = crawl_index()
    print(f"      共 {len(index)} 个疾病页", flush=True)

    done = {}
    if args.resume and OUT_FILE.exists():
        old = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        done = {d["name"]: d for d in old.get("diseases", [])}
        print(f"      续跑：已有 {len(done)} 个", flush=True)

    items = list(index.items())
    if args.limit:
        items = items[:args.limit]

    print(f"[2/2] 抓取详情页（限速 {DELAY}s/请求）...", flush=True)
    diseases, failed = [], []
    for i, (url, name) in enumerate(items, 1):
        if args.resume and name in done:
            diseases.append(done[name])
            continue
        try:
            fields = parse_fields(fetch(url))
        except Exception as e:  # noqa: BLE001
            failed.append({"name": name, "url": url, "error": str(e)[:80]})
            print(f"  [{i}/{len(items)}] FAIL {name}", flush=True)
            time.sleep(DELAY)
            continue

        kept = {k: v["values"] for k, v in fields.items()}
        diseases.append({
            "name": name,
            "url": url,
            "fields": kept,
            "relations": [{"type": v["type"], "relation": v["relation"], "targets": v["values"]}
                          for v in fields.values()],
        })
        print(f"  [{i}/{len(items)}] {name}: "
              + " ".join(f"{k}×{len(v)}" for k, v in kept.items()), flush=True)
        time.sleep(DELAY)

    payload = {
        "source": "youlai.cn/dise",
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "diseaseCount": len(diseases),
        "failed": failed,
        "diseases": diseases,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入 {OUT_FILE}　疾病 {len(diseases)} 个　失败 {len(failed)} 个")


if __name__ == "__main__":
    main()
