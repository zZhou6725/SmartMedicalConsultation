"""系统管理接口：接口1 /health 健康检查、接口2 系统状态查询。

接口2 的定位：**真实探活，不是装饰**。
每个组件都实际打一次，连不上就返回 disconnected / unavailable，
前端据此显示红点。此前前端是写死三行绿灯，Neo4j 挂了照样显示"正常"。

性能取舍：
  · 状态查询会被前端定时轮询，整体结果缓存 10 秒，避免每次刷新打 6 个探活；
  · LLM 探测只打轻量的 /models（不发起 completion，那是在烧钱），单独缓存 60 秒。
"""
import time

from fastapi import APIRouter
from openai import OpenAI

from app.config import settings
from app.retrieval import vector_store as vs
from app.store import kg_store, session_store
from app.store.db import engine

router = APIRouter()

MODEL_VERSION = "1.0.0"

# —— 结果缓存 ——
_CACHE = {"ts": 0.0, "data": None}
_CACHE_TTL = 10.0

_LLM_CACHE = {"ts": 0.0, "data": None}
_LLM_TTL = 60.0


# ---------------- 各组件探活 ----------------

def _probe_neo4j() -> dict:
    """图谱：重新数一遍节点与关系，数不出来就是没连上。"""
    try:
        entities = kg_store.run_read("MATCH (n) RETURN count(n) AS c")[0]["c"]
        relations = kg_store.run_read("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        return {"status": "connected", "entities": int(entities), "relations": int(relations)}
    except Exception:
        return {"status": "disconnected", "entities": 0, "relations": 0}


def _probe_vector() -> dict:
    """向量索引：能加载出 FAISS 索引就算 ready，顺带报条数与维度。"""
    try:
        index = vs.load()
        if index is None:
            return {"status": "unavailable", "total": 0, "dim": 0}
        return {"status": "ready", "total": int(index.ntotal), "dim": int(index.d)}
    except Exception:
        return {"status": "unavailable", "total": 0, "dim": 0}


def _probe_agent() -> dict:
    """Agent 编排：能编译出状态图就算 ready，返回节点名便于核对。"""
    try:
        from app.agent.graph import BRANCH_NODES, build_graph

        build_graph()
        nodes = ["intent_agent", *BRANCH_NODES.values(), "safety_agent"]
        return {"status": "ready", "name": "多 Agent 编排", "nodeCount": len(nodes),
                "nodes": nodes}
    except Exception:
        return {"status": "unavailable", "name": "", "nodeCount": 0, "nodes": []}


def _probe_llm() -> dict:
    """大模型：只打 /models 这种轻量接口判连通，不发起真实补全（避免每次轮询烧 token）。"""
    now = time.time()
    if _LLM_CACHE["data"] and now - _LLM_CACHE["ts"] < _LLM_TTL:
        return _LLM_CACHE["data"]

    result = {"status": "disconnected", "model": settings.LLM_MODEL}
    if settings.LLM_API_KEY:
        try:
            client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY,
                            timeout=3.0, max_retries=0)
            client.models.list()
            result["status"] = "connected"
        except Exception:
            pass

    _LLM_CACHE.update(ts=now, data=result)
    return result


def _probe_redis() -> dict:
    try:
        session_store.r.ping()
        return {"status": "connected",
                "sessions": int(session_store.r.zcard(session_store.SESSIONS_SET))}
    except Exception:
        return {"status": "disconnected", "sessions": 0}


def _probe_mysql() -> dict:
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"status": "connected"}
    except Exception:
        return {"status": "disconnected"}


# ---------------- 业务层指标 ----------------

def _business(neo4j: dict, mysql_ok: bool) -> dict:
    """业务视角：系统在干什么、干得快不快。

    与"零件是否装好"互补 —— 患者/面试官更关心今日有多少人问诊、知识库多大、答得多快。
    """
    out = {
        "todaySessions": 0,
        "totalSessions": 0,
        "totalMessages": 0,
        "avgLatencySec": 0.0,
        "knowledgeEntities": neo4j.get("entities", 0),
    }
    if not mysql_ok:
        return out

    try:
        with engine.connect() as conn:
            out["todaySessions"] = int(conn.exec_driver_sql(
                "SELECT COUNT(*) FROM chat_session WHERE DATE(create_time) = CURDATE()"
            ).scalar() or 0)
            out["totalSessions"] = int(conn.exec_driver_sql(
                "SELECT COUNT(*) FROM chat_session").scalar() or 0)
            out["totalMessages"] = int(conn.exec_driver_sql(
                "SELECT COUNT(*) FROM chat_message").scalar() or 0)
            avg_ms = conn.exec_driver_sql(
                "SELECT AVG(consume_time) FROM chat_message "
                "WHERE role = 'assistant' AND consume_time > 0"
            ).scalar()
            out["avgLatencySec"] = round(float(avg_ms) / 1000, 1) if avg_ms else 0.0
    except Exception:
        pass
    return out


# ---------------- 接口 ----------------

def _collect_status() -> dict:
    neo4j = _probe_neo4j()
    mysql = _probe_mysql()
    return {
        "neo4j": neo4j,
        "vectorIndex": _probe_vector(),
        "agent": _probe_agent(),
        "llm": _probe_llm(),
        "redis": _probe_redis(),
        "mysql": mysql,
        "business": _business(neo4j, mysql.get("status") == "connected"),
        "checkedAt": int(time.time() * 1000),
    }


@router.get("/health")
def health_check():
    """服务健康检查（接口文档 · 接口1）。"""
    return {
        "code": 1,
        "msg": "success",
        "data": {
            "status": "ok",
            "service": "smart-medical-consultation",
            "version": MODEL_VERSION,
        },
    }


@router.get("/api/system/status")
def system_status():
    """接口2：系统各组件实时状态 + 业务运行指标（结果缓存 10 秒）。"""
    now = time.time()
    if _CACHE["data"] and now - _CACHE["ts"] < _CACHE_TTL:
        return {"code": 1, "msg": "success", "data": _CACHE["data"]}

    data = _collect_status()
    _CACHE.update(ts=now, data=data)
    return {"code": 1, "msg": "success", "data": data}
