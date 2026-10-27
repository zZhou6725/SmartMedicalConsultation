"""MySQL 连接与建表（SQLAlchemy 2.0 + PyMySQL）。

定位：MySQL 是对话历史的**最终真相**，Redis 只是热缓存。
连接用 pool_pre_ping，避免容器重启/连接空闲被断开后第一个请求直接报错。
engine 在导入时不建立连接（SQLAlchemy 懒连接），所以 MySQL 没起时后端仍能启动。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

DATABASE_URL = (
    f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
    f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DB}?charset=utf8mb4"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # 取连接前先探活，MySQL 重启后自动重连
    pool_recycle=3600,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def ensure_schema():
    """建表并补齐后加的列（幂等）。

    create_all 只创建缺失的表，不会给已存在的表加列；
    因此对 chat_message.extra 这类后来新增的字段做一次 information_schema 探测后 ALTER。
    全程幂等，可以每次启动都跑。
    """
    from app.store import models  # noqa: F401  确保模型已注册到 Base.metadata

    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        cols = {row[0] for row in conn.exec_driver_sql("SHOW COLUMNS FROM chat_message")}
        if "extra" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE chat_message ADD COLUMN extra JSON NULL COMMENT '消息附加信息（如急症预警）'"
            )

        # 会话能力令牌（鉴权用）：老数据没有这一列，补列后再回填随机值，
        # 否则历史会话会变成"任何人凭 sessionId 都能读"的裸奔状态。
        sess_cols = {row[0] for row in conn.exec_driver_sql("SHOW COLUMNS FROM chat_session")}
        if "session_key" not in sess_cols:
            conn.exec_driver_sql(
                "ALTER TABLE chat_session ADD COLUMN session_key VARCHAR(64) NULL COMMENT '会话能力令牌'"
            )
            conn.exec_driver_sql("CREATE INDEX idx_session_key ON chat_session (session_key)")

    _backfill_session_keys()


def _backfill_session_keys() -> int:
    """给没有令牌的历史会话补发令牌（幂等）。"""
    import secrets

    with engine.begin() as conn:
        rows = conn.exec_driver_sql(
            "SELECT session_id FROM chat_session WHERE session_key IS NULL OR session_key = ''"
        ).fetchall()
        for (sid,) in rows:
            conn.exec_driver_sql(
                "UPDATE chat_session SET session_key = %s WHERE session_id = %s",
                (secrets.token_urlsafe(24), sid),
            )
    return len(rows)
