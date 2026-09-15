"""会话管理接口。"""
from fastapi import APIRouter

from app.store.session_store import list_sessions, delete_session   # 导入加 delete_session
router = APIRouter()


@router.get("/api/sessions")
def get_sessions(page: int = 1, pageSize: int = 10):
    rows = list_sessions()
    total = len(rows)
    start = (page - 1) * pageSize
    return {
        "code": 1,
        "msg": "success",
        "data": {"total": total, "rows": rows[start:start + pageSize]},
    }

@router.delete("/api/sessions/{sessionId}")
def remove_session(sessionId: str):
    delete_session(sessionId)                 # 同时清消息缓存 + 元信息 + 会话列表

    return {"code": 1, "msg": "success", "data": None}