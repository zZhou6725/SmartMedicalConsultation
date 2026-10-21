"""知识检索接口：GraphRAG 混合检索（接口12）/ 向量语义检索（接口13）/ 图谱结构化检索（接口14）。"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.retrieval import hybrid
from app.store import kg_store

router = APIRouter()


class HybridSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索问题或关键词")
    topK: int = Field(10, ge=1, le=50, description="每路返回结果条数")


@router.post("/api/search/hybrid")
def hybrid_search(req: HybridSearchRequest):
    """接口12：GraphRAG 混合检索（向量语义召回 + 图谱结构化扩展）。"""
    try:
        data = hybrid.hybrid_search(req.query, req.topK)
    except Exception as e:
        return {"code": 0, "msg": f"混合检索失败：{e}", "data": None}
    return {"code": 1, "msg": "success", "data": data}


class VectorSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索问题或关键词")
    topK: int = 10


@router.post("/api/search/vector")
def vector_search(req: VectorSearchRequest):
    """接口13：向量语义检索（问题 → 编码 → FAISS 召回 → 最相近的医疗实体）。"""
    results = hybrid.vector_search(req.query, req.topK)
    return {
        "code": 1,
        "msg": "success",
        "data": {"query": req.query, "results": results, "total": len(results)},
    }


class KgSearchRequest(BaseModel):
    entity: str = Field(..., min_length=1, description="实体名称")
    depth: int = Field(1, ge=1, le=3, description="扩展深度，默认 1")


@router.post("/api/search/kg")
def kg_structured_search(req: KgSearchRequest):
    """接口14：图谱结构化检索（按实体名在知识图谱中扩展关联关系）。"""
    try:
        data = kg_store.expand_entity(req.entity, req.depth)
    except Exception as e:
        return {"code": 0, "msg": f"图谱检索失败：{e}", "data": None}
    if data is None:
        return {"code": 0, "msg": "实体不存在", "data": None}
    return {"code": 1, "msg": "success", "data": data}
