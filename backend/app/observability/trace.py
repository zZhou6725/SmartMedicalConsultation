"""请求级链路追踪（可观测性）。

定位：企业级系统必须能回答「这个回答为什么是这样」。
每次对话产出一条 trace，记录意图、工具调用及成败、召回实体、各阶段耗时、
是否走了降级路径。出问题时按 trace_id 取回完整链路，而不是只盯着一句回复。

设计约束：
  · 写库是 best-effort —— 追踪失败绝不能影响问诊主流程；
  · 阶段耗时分开记（编排/检索 vs 生成），否则无法判断慢在哪；
  · fallback 标记单独留一列，用于统计"降级率"这个企业常用健康指标。
"""
import time
import uuid
from typing import Any

from app.store.db import SessionLocal
from app.store.models import RequestTrace


def new_trace_id() -> str:
    return f"tr-{uuid.uuid4().hex[:16]}"


class Trace:
    """一次请求的追踪上下文（在 request 生命周期内累积，结束时落库）。"""

    def __init__(self, question: str, session_id: str | None = None):
        self.trace_id = new_trace_id()
        self.question = question or ""
        self.session_id = session_id
        self.intent: str | None = None
        self.tool_calls: list[dict] = []
        self.retrieved: list[str] = []
        self.evidence_count = 0
        self.retrieve_ms = 0
        self.generate_ms = 0
        self.total_ms = 0
        self.fallback = False
        self.error = ""
        self._t0 = time.time()

    # ---- 采集 ----

    def mark_retrieve(self, ev: dict, elapsed_ms: int):
        """记录编排/检索阶段的结果。"""
        self.intent = ev.get("intent")
        self.retrieve_ms = elapsed_ms
        self.evidence_count = len(ev.get("evidence") or [])
        self.tool_calls = [
            {"tool": t.get("tool"), "ok": bool(t.get("ok")),
             "count": t.get("count", 0), "error": t.get("error", "")}
            for t in (ev.get("tool_log") or [])
        ]
        # 证据里 vector 源带 entity 名，用于回放"召回了什么"
        self.retrieved = [e.get("content", "")[:40] for e in (ev.get("evidence") or [])][:10]
        # 编排失败会退化成 general + 空证据，这属于降级
        self.fallback = (ev.get("intent") == "general" and self.evidence_count == 0
                         and bool(self.question))

    def mark_generate(self, elapsed_ms: int, error: str = ""):
        self.generate_ms = elapsed_ms
        if error:
            self.error = error[:255]

    def finish(self) -> int:
        self.total_ms = int((time.time() - self._t0) * 1000)
        self.persist()
        return self.total_ms

    # ---- 落库 ----

    def persist(self):
        """best-effort 写库：失败静默，绝不影响对话。"""
        try:
            with SessionLocal() as db:
                db.add(RequestTrace(
                    trace_id=self.trace_id,
                    session_id=self.session_id,
                    question=self.question,
                    intent=self.intent,
                    tool_calls=self.tool_calls,
                    retrieved=self.retrieved,
                    evidence_count=self.evidence_count,
                    retrieve_ms=self.retrieve_ms,
                    generate_ms=self.generate_ms,
                    total_ms=self.total_ms,
                    fallback=1 if self.fallback else 0,
                    error=self.error or None,
                ))
                db.commit()
        except Exception:
            pass

    def as_dict(self) -> dict:
        return {
            "traceId": self.trace_id,
            "sessionId": self.session_id,
            "question": self.question,
            "intent": self.intent,
            "toolCalls": self.tool_calls,
            "retrieved": self.retrieved,
            "evidenceCount": self.evidence_count,
            "retrieveMs": self.retrieve_ms,
            "generateMs": self.generate_ms,
            "totalMs": self.total_ms,
            "fallback": self.fallback,
            "error": self.error,
        }


# ---------------- 查询侧 ----------------

def _to_row(m: RequestTrace) -> dict:
    return {
        "traceId": m.trace_id,
        "sessionId": m.session_id,
        "question": m.question,
        "intent": m.intent,
        "toolCalls": m.tool_calls or [],
        "retrieved": m.retrieved or [],
        "evidenceCount": m.evidence_count or 0,
        "retrieveMs": m.retrieve_ms or 0,
        "generateMs": m.generate_ms or 0,
        "totalMs": m.total_ms or 0,
        "fallback": bool(m.fallback),
        "error": m.error or "",
        "createTime": m.create_time.isoformat() if m.create_time else "",
    }


def recent(limit: int = 20) -> list[dict]:
    """最近 N 条 trace（按时间倒序），供前端/运维查看。"""
    from sqlalchemy import select

    limit = max(1, min(int(limit or 20), 200))
    with SessionLocal() as db:
        rows = db.execute(
            select(RequestTrace).order_by(RequestTrace.id.desc()).limit(limit)
        ).scalars().all()
    return [_to_row(r) for r in rows]


def get(trace_id: str) -> dict | None:
    """按 trace_id 取单条链路。"""
    from sqlalchemy import select

    with SessionLocal() as db:
        m = db.execute(
            select(RequestTrace).where(RequestTrace.trace_id == trace_id)
        ).scalar_one_or_none()
    return _to_row(m) if m else None


def stats(hours: int = 24) -> dict[str, Any]:
    """近 N 小时的运行指标（企业最常看的几个）：请求量、降级率、平均耗时、P95。"""
    from sqlalchemy import func, select, text

    with SessionLocal() as db:
        q = select(
            func.count(RequestTrace.id),
            func.avg(RequestTrace.total_ms),
            func.avg(RequestTrace.retrieve_ms),
            func.avg(RequestTrace.generate_ms),
            func.sum(RequestTrace.fallback),
        ).where(text(f"create_time >= NOW() - INTERVAL {int(hours)} HOUR"))
        total, avg_total, avg_ret, avg_gen, fb = db.execute(q).one()
    total = total or 0
    return {
        "windowHours": hours,
        "requests": total,
        "fallbackRate": round((fb or 0) / total * 100, 2) if total else 0.0,
        "avgTotalMs": int(avg_total or 0),
        "avgRetrieveMs": int(avg_ret or 0),
        "avgGenerateMs": int(avg_gen or 0),
    }
