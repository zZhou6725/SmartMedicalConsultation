"""对话接口：非流式（接口4）+ SSE 流式（接口5）。

P3-3 起接入 GraphRAG 混合检索：每个用户问题先检索本地医疗知识库，
把证据拼进 system 上下文（grounded 作答），并在响应中回传 evidence 供溯源。
P3-4 起检索改由 LangGraph 多 Agent 编排驱动（意图路由 + Tool Calling）。
P3-5 起叠加急症预警与高危问题约束：命中急症时置顶红色预警，
并给大模型下发「先提示立即就医、不给用药建议」的硬性约束。

检索/编排失败不阻断对话，退化为普通对话。
"""
import time
import uuid  #随机数
import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from app.services.llm import chat_once, chat_stream as llm_stream
from app.store.session_store import load_history, load_session, save_turn
from app.services.safety import risk_rules, safety_fields
from app.agent.graph import run_agent
from app.observability.trace import Trace

log = logging.getLogger(__name__)
# Pydantic，用来定义请求体、自动做参数校验（比如 message 不能为空）


router = APIRouter()

# 免责声明
DISCLAIMER = "本回答仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。"


def retrieve(message: str, history: list | None = None) -> dict:
    """走 LangGraph 多 Agent 编排，拿到意图、证据、上下文与安全字段。

    编排内部：意图识别 → 分支（五路医疗分支内含 Tool Calling）→ 安全检查汇聚。
    编排失败时返回空证据，退化为普通对话，不阻断主流程。
    """
    empty = {"evidence": [], "context": "", "symptoms": [], "department": "",
             "intent": "general", "tool_log": []}
    try:
        state = run_agent(message, history or [])
    except Exception:
        return empty
    return {
        "evidence": state.get("evidence") or [],
        "context": state.get("context") or "",
        "symptoms": state.get("symptoms") or [],
        "department": state.get("department") or "",
        "intent": state.get("intent") or "general",
        "tool_log": state.get("tool_log") or [],
    }


def _assistant_meta(ev: dict, sf: dict) -> dict:
    """assistant 消息随消息持久化的结构化字段（Redis 与 MySQL 共用）。

    P4-1 当初只存了 emergency，导致**刷新页面或切回历史会话后症状标签、
    推荐科室、免责声明全部消失** —— 前端 done 事件有值、历史接口却没有。
    这些字段一并写进 extra，chat_repo._to_history_row 会自动平铺回消息行，
    前端无需改动即可复原。
    """
    return {
        "emergency": sf["emergency"],
        "symptoms": ev["symptoms"],
        "department": ev["department"],
        "disclaimer": sf["disclaimer"],
        "medReminder": sf["medReminder"],
    }


class ChatRequest(BaseModel):
    """请求体：message 必填、sessionId 可省、stream 固定 false。"""
    sessionId: str | None = None   # 会话ID
    message: str = Field(..., min_length=1, description="用户问题") # 不能为空 Field (非空， 长度， 注释)
    stream: bool = False  # 本接口固定非流式

@router.post("/api/chat")
def chat(req: ChatRequest):
    start = time.time()
    sid = req.sessionId or str(uuid.uuid4())   #没传 sessionId 就生成一个
    mid = f"msg-{int(time.time() * 1000)}"
    tr = Trace(req.message, sid)               # 链路追踪（best-effort 落库）

    history = load_session(sid)    #读历史
    t_ret = time.time()
    ev = retrieve(req.message, history)     #多 Agent 编排：意图 + 证据 + 安全
    tr.mark_retrieve(ev, int((time.time() - t_ret) * 1000))

    sf = safety_fields(req.message)         #确定性安全层：急症/高危约束要下发给模型
    t_gen = time.time()
    gen_err = ""
    try:
        reply = chat_once(history, req.message, ev["context"], risk_rules(req.message))
    except Exception as e:
        gen_err = f"{type(e).__name__}: {e}"
        reply = f"（调用大模型失败，请检查 LLM_API_KEY 或网络）"
    tr.mark_generate(int((time.time() - t_gen) * 1000), gen_err)

    # 追加并缓存（TTL 24h / 最近12轮）
    consume = int((time.time() - start) * 1000)
    meta = _assistant_meta(ev, sf)
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": reply, "consumeTime": consume, **meta})
    save_turn(sid, history, req.message, reply, consume, meta)   # Redis 热缓存 + MySQL 全量落库
    tr.finish()
    log.info("chat done", extra={
        "intent": ev["intent"], "session_id": sid, "latency_ms": consume,
        "retrieve_ms": tr.retrieve_ms, "generate_ms": tr.generate_ms,
        "fallback": tr.fallback, "error": gen_err or None,
    })

    return {
        "code": 1,
        "msg": "success",
        "data": {
            "sessionId": sid,
            "messageId": mid,
            "traceId": tr.trace_id,
            "reply": reply,
            "symptoms": ev["symptoms"],
            "department": ev["department"],
            "intent": ev["intent"],
            "disclaimer": DISCLAIMER,
            "medReminder": sf["medReminder"],
            "emergency": sf["emergency"],
            "consumeTime": consume,
            "evidence": ev["evidence"],
        },
    }


class ChatStreamRequest(BaseModel):
    """SSE 流式请求体：message 必填，stream 固定 true。"""
    sessionId: str | None = None
    message: str = Field(..., min_length=1)
    stream: bool = True


def sse(data: dict) -> str:
    """把 dict 转成 SSE 事件行：data: {json}\n\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/chat/stream")
async def chat_stream_handler(req: ChatStreamRequest):
    sid = req.sessionId or str(uuid.uuid4())
    mid = f"msg-{int(time.time() * 1000)}"
    history = load_session(sid)
    tr = Trace(req.message, sid)               # 链路追踪（best-effort 落库）

    def generator():
        start = time.time()
        yield sse({"type": "meta", "sessionId": sid, "messageId": mid,
                   "traceId": tr.trace_id})

        # 安全层是纯规则、微秒级，先算先发：
        # 急症警示必须第一个到达前端——等编排+工具调用+生成跑完再提示「快打 120」，
        # 方向是反的（实测那段要 8 秒）。done 帧里仍会再带一次，便于幂等与历史复原。
        sf = safety_fields(req.message)
        if sf["emergency"]["hit"]:
            yield sse({"type": "emergency", **sf["emergency"]})

        t_ret = time.time()
        ev = retrieve(req.message, history)   # 编排较慢，放在急症提示之后
        tr.mark_retrieve(ev, int((time.time() - t_ret) * 1000))

        t_gen = time.time()
        gen_err = ""
        acc = []
        try:
            for piece in llm_stream(history, req.message, ev["context"],
                                    risk_rules(req.message)):
                acc.append(piece)  # ← 补：累积文本
                yield sse({"type": "delta", "content": piece})
        except Exception as e:
            gen_err = f"{type(e).__name__}: {e}"
            yield sse({"type": "error", "code": 0, "msg": f"调用大模型失败：{e}"})
        tr.mark_generate(int((time.time() - t_gen) * 1000), gen_err)

        consume = int((time.time() - start) * 1000)
        answer = "".join(acc)
        meta = _assistant_meta(ev, sf)
        history.append({"role": "user", "content": req.message})
        history.append({"role": "assistant", "content": answer,
                        "consumeTime": consume, **meta})
        save_turn(sid, history, req.message, answer, consume, meta)
        tr.finish()
        log.info("chat stream done", extra={
            "intent": ev["intent"], "session_id": sid, "latency_ms": consume,
            "retrieve_ms": tr.retrieve_ms, "generate_ms": tr.generate_ms,
            "fallback": tr.fallback, "error": gen_err or None,
        })
        yield sse({
            "type": "done",
            "traceId": tr.trace_id,
            "consumeTime": consume,
            "symptoms": ev["symptoms"],
            "department": ev["department"],
            "intent": ev["intent"],
            "disclaimer": DISCLAIMER,
            "medReminder": sf["medReminder"],
            "emergency": sf["emergency"],
            "evidence": ev["evidence"],
        })

    return StreamingResponse(generator(), media_type="text/event-stream")

@router.get("/api/chat/messages")
def get_messages(sessionId: str):
    """会话消息列表（历史复原）：走 MySQL 全量，Redis 兜底。"""
    msgs = load_history(sessionId)
    return {"code": 1, "msg": "success", "data": {"total": len(msgs), "rows": msgs}}
