"""ORM 模型：对应 scripts/mysql_init.sql 的三张业务表。

字段与建表脚本保持一致；chat_message.extra 是后加的 JSON 列，
用来存紧急/证据这类「随消息走的附加信息」，避免每多一类元数据就加一列。
"""
from sqlalchemy import (
    JSON, BigInteger, Column, DateTime, Enum, Float, Index, Integer, String, Text, func,
)

from app.store.db import Base


class ChatSession(Base):
    """问诊会话表。"""
    __tablename__ = "chat_session"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(255), default="新对话")
    create_time = Column(DateTime, server_default=func.now())
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    """对话消息明细表（全量持久化，Redis 过期后从这里恢复）。"""
    __tablename__ = "chat_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False)
    role = Column(Enum("user", "assistant", name="role_enum"), nullable=False)
    content = Column(Text, nullable=False)
    consume_time = Column(Integer, default=0)
    create_time = Column(DateTime, server_default=func.now())
    extra = Column(JSON, nullable=True)      # {"emergency": {...}} 等附加信息

    __table_args__ = (Index("idx_session_time", "session_id", "create_time"),)


class EvalRecord(Base):
    """自动化评估记录表（P4-2 评估门禁用）。"""
    __tablename__ = "eval_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    pass_status = Column(Integer, default=0)
    eval_score = Column(Float, default=0)
    create_time = Column(DateTime, server_default=func.now())
