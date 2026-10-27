# 后端镜像：FastAPI + 向量检索 + 图谱
# 构建上下文是仓库根目录（见 docker-compose.yml 的 context: .），
# 因为 requirements.txt 在根目录、knowledge/ 也在根目录。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # 容器内项目根目录固定在 /app（config.BASE_DIR 默认按文件层级推算，
    # 在镜像里会算成 /，所以用 PROJECT_ROOT 显式覆盖）
    PROJECT_ROOT=/app

WORKDIR /app/backend

# 健康检查探针需要 curl
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖再拷代码，利用层缓存：改代码不会触发重装依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/ /app/backend/
# knowledge/ 里只有构建脚本；向量索引体积大且在 .gitignore 中，
# 运行时通过数据卷挂载到 /app/knowledge/index（见 compose 的 volumes）。
COPY knowledge/ /app/knowledge/

EXPOSE 8000

# 存活探针用 /healthz（不查依赖）；就绪判定交给 compose 的 /readyz
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
