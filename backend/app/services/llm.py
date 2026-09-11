"""大模型调用：统一封装非流式 + 流式。"""
from openai import OpenAI

from app.config import settings

# OpenAI 兼容客户端：base_url 指向 DeepSeek（或本地 vLLM）
client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY)

# 系统提示词：专业、克制、不使用 emoji
SYSTEM_PROMPT = (
    "你是一个专业的医疗健康咨询助手。请用简体中文回答。"
    "回答要简洁、要点化（用分点/列表），控制在 5 行以内，不要长篇大论；"
    "只做健康咨询与就医指导，不能替代专业医疗诊断；"
    "禁止使用任何 emoji、表情符号，保持纯文本专业输出。"
)


def build_messages(history: list, user_text: str) -> list:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history)
    msgs.append({"role": "user", "content": user_text})
    return msgs


def chat_once(history: list, user_text: str) -> str:
    """非流式：一次返回完整回复。"""
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=build_messages(history, user_text),
    )
    return resp.choices[0].message.content or ""


def chat_stream(history: list, user_text: str):
    """流式生成器：逐块 yield 文本，用于 SSE。"""
    stream = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=build_messages(history, user_text),
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content