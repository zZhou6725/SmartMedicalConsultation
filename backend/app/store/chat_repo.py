"""MySQL 对话全量持久化（Redis 之外的最终真相）。

分层职责：
  Redis  —— 热缓存，最近 12 轮 / TTL 24h，负责「快」；
  MySQL  —— 全量落库，负责「不丢」，服务重启或 Redis 过期后历史仍可恢复。

本模块只做 MySQL 侧读写，失败一律向上抛，由 session_store 决定是否兜底。
"""
from sqlalchemy import delete, select

from app.store.db import SessionLocal
from app.store.models import ChatMessage, ChatSession

MAX_TITLE = 30


def _title_of(text: str) -> str:
    """会话标题取首次提问的前 30 字。"""
    return (text or "新对话").strip()[:MAX_TITLE] or "新对话"


def _to_history_row(msg: ChatMessage) -> dict:
    """ORM 行 → 前端/LLM 可直接用的消息字典（与 Redis 里的结构保持一致）。"""
    row = {"role": msg.role, "content": msg.content}
    if msg.role == "assistant" and msg.consume_time:
        row["consumeTime"] = msg.consume_time
    if msg.extra:
        row.update(msg.extra)          # 例如 {"emergency": {...}}，切换会话时红牌可复原
    return row


def append_turn(session_id: str, user_text: str, assistant_text: str,
                consume_time: int = 0, extra: dict | None = None) -> int:
    """落一次问答（user + assistant 两条），并同步会话记录。返回写入条数。"""
    with SessionLocal() as db:
        sess = db.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        ).scalar_one_or_none()

        if sess is None:
            db.add(ChatSession(session_id=session_id, title=_title_of(user_text)))
        else:
            sess.title = sess.title if (sess.title and sess.title != "新对话") else _title_of(user_text)
            sess.update_time = None      # 置空 → 交给 ON UPDATE CURRENT_TIMESTAMP 刷新

        db.add(ChatMessage(session_id=session_id, role="user",
                           content=user_text, consume_time=0))
        db.add(ChatMessage(session_id=session_id, role="assistant",
                           content=assistant_text, consume_time=consume_time,
                           extra=extra))
        db.commit()
        return 2


def load_messages(session_id: str) -> list:
    """按时间正序读全会话消息（用于恢复历史）。"""
    with SessionLocal() as db:
        rows = db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        ).scalars().all()
    return [_to_history_row(m) for m in rows]


def list_sessions(limit: int = 50) -> list:
    """会话列表，按更新时间倒序（字段名与前端约定一致；时间转毫秒时间戳）。"""
    with SessionLocal() as db:
        rows = db.execute(
            select(ChatSession).order_by(ChatSession.update_time.desc()).limit(limit)
        ).scalars().all()

    out = []
    for s in rows:
        out.append({
            "sessionId": s.session_id,
            "title": s.title or "新对话",
            "createTime": int(s.create_time.timestamp() * 1000) if s.create_time else 0,
            "updateTime": int(s.update_time.timestamp() * 1000) if s.update_time else 0,
        })
    return out


def delete_session(session_id: str) -> int:
    """级联删除会话与其全部消息，返回删除的消息条数。"""
    with SessionLocal() as db:
        deleted = db.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id)
        ).rowcount
        db.execute(delete(ChatSession).where(ChatSession.session_id == session_id))
        db.commit()
    return deleted or 0
