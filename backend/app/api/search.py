"""知识检索接口。"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.retrieval.embeddings import encode
from app.retrieval import vector_store as vs

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