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


class RequestTrace(Base):
    """请求级链路追踪表（可观测性）。

    企业级系统与 demo 的关键差别之一：能不能回答「这个回答为什么是这样」。
    每次对话落一条：意图、工具调用、召回实体、各阶段耗时、是否走了降级。
    出问题时按 trace_id 取回完整链路，而不是只看一句回复。
    """
    __tablename__ = "request_trace"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=False, unique=True, index=True)
    session_id = Column(String(64), index=True)
    question = Column(Text, nullable=False)
    intent = Column(String(32))
    tool_calls = Column(JSON)          # [{tool, ok, count, ms}]
    retrieved = Column(JSON)           # 召回实体名列表
    evidence_count = Column(Integer, default=0)
    retrieve_ms = Column(Integer, default=0)    # 编排+检索耗时
    generate_ms = Column(Integer, default=0)    # 大模型生成耗时
    total_ms = Column(Integer, default=0)
    fallback = Column(Integer, default=0)       # 1=走了降级路径
    error = Column(String(255))
    create_time = Column(DateTime, server_default=func.now(), index=True)
