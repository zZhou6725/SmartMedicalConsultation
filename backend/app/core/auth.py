"""鉴权：管理接口令牌 + 会话归属校验。

为什么需要：
  · 所有接口原本完全敞开 —— 任何能访问到 8000 的人都能触发评估（烧 token）、
    读全量问诊历史、删别人的会话。健康数据属于敏感信息，不能靠"没人知道地址"。
  · 这里只做**最小可用**的两层，不做完整用户体系：
      1. 管理类接口（评估/图谱/链路）→ 需要 X-Admin-Token；
      2. 会话读写 → 需要服务端签发的 X-Session-Key（能力令牌）。

设计取舍：
  · 比较一律用 hmac.compare_digest（防时序侧信道）；
  · ADMIN_TOKEN 未配置时**只放行本机**，而不是"放行所有人" ——
    默认安全，本地开发零配置可用，一旦对外就必须显式设置。
"""
import hmac
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import settings

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def admin_allowed(provided: str | None, configured: str, is_local: bool) -> tuple[bool, str]:
    """管理权限判定（纯函数，便于单测）。

    返回 (是否放行, 拒绝原因)。
      配置了令牌 → 必须匹配；
      未配置    → 只允许本机，其余一律拒绝。
    """
    configured = (configured or "").strip()
    if configured:
        if provided and hmac.compare_digest(provided, configured):
            return True, ""
        return False, "管理令牌无效或缺失（请求头 X-Admin-Token）"
    if is_local:
        return True, ""
    return False, "服务端未配置 ADMIN_TOKEN，管理接口仅允许本机访问"


def _client_is_local(request: Request) -> bool:
    host = getattr(getattr(request, "client", None), "host", None) or ""
    return host in _LOCAL_HOSTS


def require_admin(request: Request) -> None:
    """FastAPI 依赖：管理类接口的守卫（不通过直接 403）。"""
    ok, reason = admin_allowed(
        request.headers.get("X-Admin-Token"),
        settings.ADMIN_TOKEN,
        _client_is_local(request),
    )
    if not ok:
        raise HTTPException(status_code=403, detail=reason)


def is_admin(request: Request) -> bool:
    """当前请求是否具备管理权限（用于"能看全量"这类分支判断）。"""
    ok, _ = admin_allowed(
        request.headers.get("X-Admin-Token"),
        settings.ADMIN_TOKEN,
        _client_is_local(request),
    )
    return ok


def new_session_key() -> str:
    """签发会话能力令牌（不可猜，等价于"这个会话的钥匙"）。"""
    return secrets.token_urlsafe(24)


def session_key_ok(expected: str | None, provided: str | None) -> bool:
    """会话令牌校验：服务端有 key 就必须匹配；服务端无 key（历史数据）视为不设防。"""
    if not expected:
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


@dataclass
class SessionAuth:
    """会话请求的身份信息。"""
    session_id: str
    is_new: bool
