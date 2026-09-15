"""Redis 会话热缓存：最近 12 轮、TTL 24h。"""
import json
import time
import redis

from app.config import settings

r = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True,
)

KEY_PREFIX = "medical:session:"
META_PREFIX = "medical:session:meta:"
SESSIONS_SET = "medical:sessions"        # 有序集合：score = 更新时间戳（用于排序会话）
MAX_ROUNDS = 12


def _key(session_id: str) -> str:
    return f"{KEY_PREFIX}{session_id}"


def _meta_key(session_id: str) -> str:
    return f"{META_PREFIX}{session_id}"

def save_session(session_id: str, messages: list):
    """保存会话消息（最近12轮 + TTL 24h），并更新会话列表与元信息。"""
    capped = messages[-MAX_ROUNDS * 2:]
    r.set(_key(session_id), json.dumps(capped, ensure_ascii=False), ex=settings.REDIS_TTL)

    now = int(time.time() * 1000)
    title = next((m["content"] for m in capped if m["role"] == "user"), "新对话")
    r.zadd(SESSIONS_SET, {session_id: now})                       # 加入会话列表
    r.hsetnx(_meta_key(session_id), "createTime", now)            # 首次创建时间
    r.hset(_meta_key(session_id), mapping={"title": title[:30], "updateTime": now})
    r.expire(_meta_key(session_id), settings.REDIS_TTL)


def load_session(session_id: str) -> list:
    """读取会话消息，无则返回空列表。"""
    raw = r.get(_key(session_id))
    return json.loads(raw) if raw else []

def list_sessions() -> list:
    """会话列表，按更新时间倒序。"""
    rows = []
    for sid in r.zrevrange(SESSIONS_SET, 0, -1):
        meta = r.hgetall(_meta_key(sid))
        if not meta:                                              # 消息已过期 → 清理
            r.zrem(SESSIONS_SET, sid)
            continue
        rows.append({
            "sessionId": sid,
            "title": meta.get("title", "新对话"),
            "createTime": int(meta.get("createTime", 0)),
            "updateTime": int(meta.get("updateTime", 0)),
        })
    return rows

def delete_session(session_id: str):
    r.delete(_key(session_id))