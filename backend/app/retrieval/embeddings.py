"""BGE-M3 文本向量编码（单例懒加载）。"""
import os
from functools import lru_cache

from app.config import settings

# 模型已在本地缓存时强制离线：避免 huggingface_hub 联网校验卡在外网请求上。
# 但容器首次启动需要下载模型（EMBEDDING_LOCAL_ONLY=0），此时绝不能关网，
# 否则会直接加载失败。所以离线开关必须跟着配置走。
if settings.EMBEDDING_LOCAL_ONLY:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from sentence_transformers import SentenceTransformer   # noqa: E402  必须在设置离线变量之后导入


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """整个进程只加载一次模型（首次 10~30 秒，之后复用，避免每次重载）。"""
    return SentenceTransformer(settings.EMBEDDING_MODEL,
                               local_files_only=settings.EMBEDDING_LOCAL_ONLY)


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
