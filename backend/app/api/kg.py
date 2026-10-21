"""知识图谱接口：实体详情（接口15）/ 图谱全文搜索（接口16）/ 图谱统计（接口17）。"""
from fastapi import APIRouter, Query

from app.store import kg_store

router = APIRouter(prefix="/api/kg", tags=["知识图谱"])


@router.get("/entity/{type}/{name}")
def entity_detail(type: str, name: str):
    """接口15：实体详情查询（实体名称 / 类型 / 描述 / 关联关系）。"""
    try:
        data = kg_store.get_entity(type, name)
    except Exception as e:
        return {"code": 0, "msg": f"图谱查询失败：{e}", "data": None}
    if data is None:
        return {"code": 0, "msg": "实体不存在或类型不在白名单内", "data": None}
    return {"code": 1, "msg": "success", "data": data}


@router.get("/search")
def kg_search(keyword: str = Query(..., min_length=1), limit: int = 20):
    """接口16：图谱全文搜索（按关键词模糊匹配实体）。"""
    try:
        results = kg_store.search_nodes(keyword, limit)
    except Exception as e:
        return {"code": 0, "msg": f"图谱搜索失败：{e}", "data": None}
    return {"code": 1, "msg": "success", "data": {"total": len(results), "results": results}}


@router.get("/stats")
def kg_stats():
    """接口17：图谱统计（节点/关系总数 + 类型分布），供前端状态栏展示。"""
    try:
        data = kg_store.get_stats()
    except Exception as e:
        return {"code": 0, "msg": f"图谱统计失败：{e}", "data": None}
    return {"code": 1, "msg": "success", "data": data}
