"""P3-1 小测试：验证 BGE-M3 + FAISS 语义检索。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.retrieval.embeddings import encode          # noqa: E402
from app.retrieval import vector_store as vs          # noqa: E402

# ① 几段"医疗知识"
docs = [
    "偏头痛：反复发作的搏动性头痛，多见于青年女性",
    "高血压：血压持续升高，常见头晕头痛",
    "胃炎：上腹疼痛、反酸，与饮食有关",
    "糖尿病：多饮多尿、体重下降",
    "布洛芬：解热镇痛药，可用于发热和头痛",
]

# ② 编码 → 建索引
vecs = encode(docs)
vs.build(vecs, [{"text": d} for d in docs])
print(f"索引条数: {len(docs)}  维度: {vecs.shape[1]}")

# ③ 用"口语化"问题检索（注意：故意用"头疼"而不是"头痛"）
query = "我头疼应该挂什么科"
results = vs.search(encode(query), top_k=3)
print(f"\n查询: {query}")
for r in results:
    print(f"  {r['score']:.4f}  {r['meta']['text']}")