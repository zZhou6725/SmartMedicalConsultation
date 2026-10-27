"""会话管理接口。

鉴权口径（与 app/core/auth.py 一致）：
  · 管理员（配置了 X-Admin-Token 且匹配，或未配置时从本机访问）→ 可看全量会话；
  · 普通调用方 → **只能看到自己持有令牌的会话**（请求头 X-Session-Keys，逗号分隔）。
  · 删除会话 / 读取会话消息 → 必须持有该会话的令牌。
没有这层，知道 sessionId 就能读光别人的问诊记录 —— 健康数据不能这样裸奔。
"""
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.auth import is_admin, session_key_ok
from app.store import chat_repo
from app.store.session_store import list_sessions, delete_session

router = APIRouter()


@router.get("/api/sessions")
def get_sessions(request: Request,
                 page: int = 1,
                 pageSize: int = 10,
                 x_session_keys: str | None = Header(default=None, alias="X-Session-Keys")):
    rows = list_sessions()

    # 非管理员：只返回它自己持有令牌的会话，而不是全部
    if not is_admin(request):
        held = {k.strip() for k in (x_session_keys or "").split(",") if k.strip()}
        rows = [r for r in rows if r.get("sessionKey") and r["sessionKey"] in held]
        for r in rows:                     # 返回体里不必回显令牌
            r.pop("sessionKey", None)
    else:
        for r in rows:
            r.pop("sessionKey", None)

    total = len(rows)
    start = max(0, (page - 1) * pageSize)
    return {
        "code": 1,
        "msg": "success",
        "data": {"total": total, "rows": rows[start:start + pageSize]},
    }


@router.delete("/api/sessions/{sessionId}")
def remove_session(sessionId: str,
                   x_session_key: str | None = Header(default=None, alias="X-Session-Key")):
    try:
        expected = chat_repo.get_session_key(sessionId)
    except Exception:
        expected = None
    if not session_key_ok(expected, x_session_key):
        raise HTTPException(status_code=403, detail="会话令牌无效，无法删除该会话")

    delete_session(sessionId)                 # 同时清消息缓存 + 元信息 + 会话列表
    return {"code": 1, "msg": "success", "data": None}
