"""知识检索接口：向量语义检索（接口13）/ 图谱结构化检索（接口14）。"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.retrieval.embeddings import encode
from app.retrieval import vector_store as vs
from app.store import kg_store

router = APIRouter()


class VectorSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索问题或关键词")
    topK: int = 10


@router.post("/api/search/vector")
def vector_search(req: VectorSearchRequest):
    """向量语义检索：问题 → 编码 → FAISS 召回 → 返回最相近的医疗实体。"""
    hits = vs.search(encode(req.query), top_k=req.topK)
    results = [
        {
            "entity": h["meta"].get("entity", ""),
            "type": (h["meta"].get("type", "") or "").lower(),   # Disease → disease
            "score": round(h["score"], 4),
            "content": h["meta"].get("content", ""),
        }
        for h in hits
    ]
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
    """图谱结构化检索（接口14）：按实体名在知识图谱中扩展关联关系。"""
    try:
        data = kg_store.expand_entity(req.entity, req.depth)
    except Exception as e:
        return {"code": 0, "msg": f"图谱检索失败：{e}", "data": None}
    if data is None:
        return {"code": 0, "msg": "实体不存在", "data": None}
    return {"code": 1, "msg": "success", "data": data}
