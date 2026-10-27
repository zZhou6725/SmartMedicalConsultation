"""可观测性接口：链路查询与运行指标。

与 /api/system/status（组件探活）互补：
  · status 回答「零件是否装好」；
  · trace 回答「每次请求发生了什么、错在哪一步」。
"""
from fastapi import APIRouter, Query

from app.observability import trace

router = APIRouter(prefix="/api/trace", tags=["可观测性"])


@router.get("/stats")
def trace_stats(hours: int = Query(24, ge=1, le=720, description="统计窗口（小时）")):
    """近 N 小时运行指标：请求量 / 降级率 / 分阶段平均耗时。"""
    try:
        return {"code": 1, "msg": "success", "data": trace.stats(hours)}
    except Exception as e:
        return {"code": 0, "msg": f"查询失败：{e}", "data": None}


@router.get("/recent")
def trace_recent(limit: int = Query(20, ge=1, le=200)):
    """最近 N 条请求链路。"""
    try:
        return {"code": 1, "msg": "success", "data": {"rows": trace.recent(limit)}}
    except Exception as e:
        return {"code": 0, "msg": f"查询失败：{e}", "data": None}


@router.get("/{trace_id}")
def trace_detail(trace_id: str):
    """按 trace_id 取单条链路详情（回放用）。"""
    try:
        row = trace.get(trace_id)
    except Exception as e:
        return {"code": 0, "msg": f"查询失败：{e}", "data": None}
    if row is None:
        return {"code": 0, "msg": "链路不存在", "data": None}
    return {"code": 1, "msg": "success", "data": row}
