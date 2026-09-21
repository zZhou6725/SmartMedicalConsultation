"""BGE-M3 文本向量编码（单例懒加载）。"""
"""BGE-M3 文本向量编码（单例懒加载）。"""
import os

# 模型已在本地缓存 → 强制离线：避免 transformers/huggingface_hub 联网校验（否则会卡在 huggingface.co）
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """整个进程只加载一次模型（首次 10~30 秒，之后复用，避免每次重载）。"""
    # local_files_only=True：只用本地缓存，跳过联网检查，加载更快
    return SentenceTransformer(settings.EMBEDDING_MODEL, local_files_only=True)


def encode(texts, normalize: bool = True):
    """文本 → 向量。传 str 返回 (1024,)；传 list 返回 (N, 1024)。"""
    single = isinstance(texts, str)
    if single:
        texts = [texts]
    vecs = get_model().encode(
        texts,
        normalize_embeddings=normalize,      # 归一化后，"内积"就等于"余弦相似度"
        show_progress_bar=False,
    )
    return vecs[0] if single else vecs