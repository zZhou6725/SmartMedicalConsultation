"""系统管理接口：/health 健康检查。"""
from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
def health_check():
    """服务健康检查（接口文档 · 接口1 /health）。"""
    return {
        "code": 1,
        "msg": "success",
        "data": {
            "status": "ok",
            "service": "smart-medical-consultation",
            "version": "1.0.0",
        },
    }
