"""智慧问诊 Agent 系统 - FastAPI 入口。

P0-3：项目初始化 + /health 健康检查。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.system import router as system_router
from app.config import settings

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
app.include_router(system_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
