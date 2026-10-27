"""全局配置：从项目根目录 .env 加载环境变量。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（backend/app/config.py 向上两级 = D:\Python-ai\Project\SmartMedicalConsultation）
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    """服务与中间件连接配置。"""

    # 服务
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    ENV: str = os.getenv("ENV", "dev")

    # MySQL
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3307"))  # 本机 3306 被占用，映射 3307
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "123456")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "medical_consult")

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_TTL: int = int(os.getenv("REDIS_TTL", "86400"))

    # Neo4j
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "123456")

    # 大模型
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # 向量模型
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))

    # ---------------- 检索与生成预算（可调，改 .env 即生效）----------------
    # 证据预算：trace 实测一次问诊曾灌进 45 条证据，token 成本与延迟随之膨胀。
    # 但也不能砍太狠 —— 单个实体的画像（如「布洛芬」16 条关系）被截断会直接
    # 丢掉副作用/禁忌这类关键事实（实测：砍到 12 条时 2 条用例回归失败）。
    # 20 条 ≈ 保留完整实体画像，同时仍比无预算减少一半上下文。
    EVIDENCE_MAX_ITEMS: int = int(os.getenv("EVIDENCE_MAX_ITEMS", "20"))
    EVIDENCE_MAX_CHARS: int = int(os.getenv("EVIDENCE_MAX_CHARS", "2400"))
    # 检索相关性下限：低于此分数的命中视为噪声，不作为症状标签/科室依据
    RELEVANCE_FLOOR: float = float(os.getenv("RELEVANCE_FLOOR", "0.6"))
    # 词面命中加成：查询里直接出现实体名时给相似度加权
    LEXICAL_BOOST: float = float(os.getenv("LEXICAL_BOOST", "0.15"))
    # 同族去重阈值（字符级 Jaccard）
    FAMILY_JACCARD: float = float(os.getenv("FAMILY_JACCARD", "0.7"))
    # 单次工具调用的返回条数
    TOOL_TOP_K: int = int(os.getenv("TOOL_TOP_K", "5"))

    # ---------------- 超时与熔断（依赖外部服务必须假设它会挂）----------------
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60"))       # 单次补全超时（秒）
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "1"))
    LLM_BREAKER_THRESHOLD: int = int(os.getenv("LLM_BREAKER_THRESHOLD", "5"))
    LLM_BREAKER_COOLDOWN: int = int(os.getenv("LLM_BREAKER_COOLDOWN", "60"))
    DB_TIMEOUT: float = float(os.getenv("DB_TIMEOUT", "10"))         # Neo4j 查询超时

    # ---------------- 日志 ----------------
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_JSON: bool = os.getenv("LOG_JSON", "1").lower() not in ("0", "false", "no")


settings = Settings()
