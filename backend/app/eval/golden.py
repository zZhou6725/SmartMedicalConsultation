"""金标集加载。"""
import json
from pathlib import Path

from app.config import BASE_DIR

EVAL_DIR = BASE_DIR / "eval"
REPORT_DIR = EVAL_DIR / "reports"

DATASETS = {
    "golden53": EVAL_DIR / "golden_set.json",
}


def load_golden(dataset_id: str = "golden53") -> dict:
    """读金标集，返回 {datasetId, version, cases: [...]}。"""
    path = DATASETS.get(dataset_id)
    if path is None:
        raise FileNotFoundError(f"未登记的金标集: {dataset_id}（可用: {list(DATASETS)}）")
    if not path.exists():
        raise FileNotFoundError(f"金标集文件不存在: {path}")
    return json.loads(Path(path).read_text(encoding="utf-8"))
