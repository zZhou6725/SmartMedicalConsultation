import time
import uuid  #随机数
import json

from fastapi import APIRouter
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
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
    reply = (
        f"（模拟回复）已收到您的问题：{req.message}。"
        "这是后端返回的固定模拟回复，后续会替换为真实智能问诊答案。"
    )
    consume = int((time.time() - start) * 1000)  # 简单计时（毫秒）
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
async def chat_stream(req: ChatStreamRequest):
    sid = req.sessionId or str(uuid.uuid4())
    mid = f"msg-{int(time.time() * 1000)}"
    full = (
        f"（流式模拟回复）已收到您的问题：{req.message}。"
        "这是后端分块推送的流式回复。"
    )

    def generator():
        start = time.time()
        yield sse({"type": "meta", "sessionId": sid, "messageId": mid})
        # 把整句切成小块，模拟 LLM 逐字输出
        for ch in (full[i:i + 3] for i in range(0, len(full), 3)):
            yield sse({"type": "delta", "content": ch})
            time.sleep(0.03)                # 模拟生成间隔
        consume = int((time.time() - start) * 1000)
        yield sse({
            "type": "done",
            "consumeTime": consume,
            "symptoms": ["头痛", "头晕"],
            "department": "神经内科",
            "disclaimer": DISCLAIMER,
            "evidence": [],
        })

    return StreamingResponse(generator(), media_type="text/event-stream")