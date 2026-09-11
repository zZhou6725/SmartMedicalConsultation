"""Redis 会话热缓存：最近 12 轮、TTL 24h。"""
import json

import redis

from app.config import settings

r = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True,
)

KEY_PREFIX = "medical:session:"
MAX_ROUNDS = 12          # 只缓存最近 12 轮（用户+回答=2 条，共 24 条消息）


def _key(session_id: str) -> str:
    return f"{KEY_PREFIX}{session_id}"


def save_session(session_id: str, messages: list):
    """覆盖式保存会话消息，只留最近 12 轮，设置 TTL 24h。"""
    capped = messages[-MAX_ROUNDS * 2:]                 # 留最近 12 轮
    r.set(_key(session_id), json.dumps(capped, ensure_ascii=False), ex=settings.REDIS_TTL)


def load_session(session_id: str) -> list:
    """读取会话消息，无则返回空列表。"""
    raw = r.get(_key(session_id))
    return json.loads(raw) if raw else []


def delete_session(session_id: str):
    r.delete(_key(session_id))