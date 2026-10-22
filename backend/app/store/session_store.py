"""会话存储：Redis 热缓存 + MySQL 全量持久化（P4-1）。

分层：
  Redis  —— 最近 12 轮 / TTL 24h，负责「快」，喂给大模型的上下文从这里取；
  MySQL  —— 全量落库，负责「不丢」，服务重启或 Redis 过期后历史仍可恢复。

读写策略：
  · 写：save_turn() 同时写 Redis 与 MySQL；MySQL 写失败不影响对话主流程；
  · 读（喂模型）：Redis 优先，未命中回 MySQL 并回填缓存（只取最近 12 轮，控制上下文长度）；
  · 读（给前端看）：load_history() 走 MySQL 拿全量，Redis 只作为兜底；
  · 会话列表：MySQL 为准（重启后仍可见），MySQL 不可用时退回 Redis 有序集合。
"""
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
    """写 Redis 热缓存（最近12轮 + TTL 24h），并更新会话列表与元信息。"""
    capped = messages[-MAX_ROUNDS * 2:]
    r.set(_key(session_id), json.dumps(capped, ensure_ascii=False), ex=settings.REDIS_TTL)

    now = int(time.time() * 1000)
    title = next((m["content"] for m in capped if m["role"] == "user"), "新对话")
    r.zadd(SESSIONS_SET, {session_id: now})                       # 加入会话列表
    r.hsetnx(_meta_key(session_id), "createTime", now)            # 首次创建时间
    r.hset(_meta_key(session_id), mapping={"title": title[:30], "updateTime": now})
    r.expire(_meta_key(session_id), settings.REDIS_TTL)


def save_turn(session_id: str, messages: list, user_text: str, assistant_text: str,
              consume_time: int = 0, extra: dict | None = None):
    """落一次问答：Redis 热缓存 + MySQL 全量持久化。

    MySQL 写失败只影响「下次重启能否恢复」，不影响本次对话，
    所以这里吞掉异常 —— 不能因为持久化层挂了就让整个问诊不可用。
    """
    save_session(session_id, messages)

    from app.store import chat_repo
    try:
        chat_repo.append_turn(session_id, user_text, assistant_text,
                              consume_time=consume_time, extra=extra)
    except Exception:
        pass


def load_session(session_id: str) -> list:
    """读会话消息（喂给大模型的上下文）：Redis 优先，未命中回 MySQL 并回填缓存。"""
    raw = r.get(_key(session_id))
    if raw:
        return json.loads(raw)

    from app.store import chat_repo
    try:
        rows = chat_repo.load_messages(session_id)
    except Exception:
        return []
    if not rows:
        return []

    capped = rows[-MAX_ROUNDS * 2:]        # 只回填最近 12 轮，避免上下文过长
    try:
        r.set(_key(session_id), json.dumps(capped, ensure_ascii=False), ex=settings.REDIS_TTL)
    except Exception:
        pass
    return capped


def load_history(session_id: str) -> list:
    """读全会话历史（给前端展示）：MySQL 全量优先，Redis 兜底。"""
    from app.store import chat_repo
    try:
        rows = chat_repo.load_messages(session_id)
        if rows:
            return rows
    except Exception:
        pass

    raw = r.get(_key(session_id))
    return json.loads(raw) if raw else []


def list_sessions(limit: int = 50) -> list:
    """会话列表：MySQL 为准（服务重启后仍可见）；MySQL 不可用或为空时退回 Redis。"""
    from app.store import chat_repo
    try:
        rows = chat_repo.list_sessions(limit)
        if rows:
            return rows
    except Exception:
        pass

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
    """删除会话：MySQL 级联删 + 清 Redis 缓存与列表项。"""
    from app.store import chat_repo
    try:
        chat_repo.delete_session(session_id)
    except Exception:
        pass

    r.delete(_key(session_id))          # 删消息
    r.delete(_meta_key(session_id))     # 删元信息（标题/时间）
    r.zrem(SESSIONS_SET, session_id)    # 从会话列表移除
