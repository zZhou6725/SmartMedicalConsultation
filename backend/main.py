"""智慧问诊 Agent 系统 - FastAPI 入口。

P0-3：项目初始化 + /health 健康检查。
"""
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.system import router as system_router
from app.api.chat import router as chat_router
from app.api.sessions import router as sessions_router
from app.api.search import router as search_router
from app.api.kg import router as kg_router
from app.api.eval_api import router as eval_router
from app.api.trace_api import router as trace_router
from app.config import settings
from app.core.auth import require_admin
from app.core.logging import setup_logging

# 结构化日志必须在其他模块打日志之前初始化
setup_logging(settings.LOG_LEVEL, settings.LOG_JSON)
log = logging.getLogger("app")

app = FastAPI(
    title="智慧问诊 Agent 系统",
    description="可信、可控、可溯源的智慧问诊 Agent 系统后端",
    version="1.0.0",
)

# CORS：开发期允许前端 Vite（localhost:5173）跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
# 公开：健康探针、系统状态、对话、会话、混合检索（前端直接使用）
app.include_router(system_router)
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(search_router)

# 管理类：评估（烧 token）、图谱（可看全库）、链路追踪（含 question 原文）
# → 统一要求 X-Admin-Token；未配置令牌时仅允许本机访问
app.include_router(kg_router, dependencies=[Depends(require_admin)])
app.include_router(eval_router, dependencies=[Depends(require_admin)])
app.include_router(trace_router, dependencies=[Depends(require_admin)])


@app.on_event("startup")
def _init_mysql():
    """启动时建表/补列（幂等）。

    MySQL 不可用不影响服务启动 —— 此时对话仍可跑，只是历史无法跨重启恢复。
    """
    from app.store.db import ensure_schema

    try:
        ensure_schema()
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
