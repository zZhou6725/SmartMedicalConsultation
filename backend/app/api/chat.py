import time
import uuid  #随机数
import json

from fastapi import APIRouter
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from app.services.llm import chat_once, chat_stream as llm_stream
from app.store.session_store import load_session, save_session
from app.services.safety import safety_fields
# Pydantic，用来定义请求体、自动做参数校验（比如 message 不能为空）


router = APIRouter()

# 免责声明
DISCLAIMER = "本回答仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。"

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

    history = load_session(sid)    #读历史
    try:
        reply = chat_once(history, req.message)
    except Exception as e:
        reply = f"（调用大模型失败，请检查 LLM_API_KEY 或网络）"

    # 追加并缓存（TTL 24h / 最近12轮）
    consume = int((time.time() - start) * 1000)
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": reply, "consumeTime": consume})  # ← 带上耗时
    save_session(sid, history)

    sf = safety_fields(req.message)

    return {
        "code": 1,
        "msg": "success",
        "data": {
            "sessionId": sid,
            "messageId": mid,
            "reply": reply,
            "symptoms": ["头痛", "头晕"],
            "department": "神经内科",
            "disclaimer": DISCLAIMER,
            "medReminder": sf["medReminder"],
            "consumeTime": consume,
            "evidence": [],
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

    def generator():
        start = time.time()
        yield sse({"type": "meta", "sessionId": sid, "messageId": mid})
        acc = []
        try:
            for piece in llm_stream(history, req.message):
                acc.append(piece)  # ← 补：累积文本
                yield sse({"type": "delta", "content": piece})
        except Exception as e:
            yield sse({"type": "error", "code": 0, "msg": f"调用大模型失败：{e}"})
        consume = int((time.time() - start) * 1000)
        history.append({"role": "user", "content": req.message})
        history.append({"role": "assistant", "content": "".join(acc), "consumeTime": consume})
        save_session(sid, history)
        sf = safety_fields(req.message)
        yield sse({
            "type": "done",
            "consumeTime": consume,
            "symptoms": ["头痛", "头晕"],
            "department": "神经内科",
            "disclaimer": DISCLAIMER,
            "medReminder": sf["medReminder"],
            "evidence": [],
        })

    return StreamingResponse(generator(), media_type="text/event-stream")

@router.get("/api/chat/messages")
def get_messages(sessionId: str):
    msgs = load_session(sessionId)
    return {"code": 1, "msg": "success", "data": {"total": len(msgs), "rows": msgs}}