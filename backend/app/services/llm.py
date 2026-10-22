"""大模型调用：统一封装非流式 + 流式，并支持注入检索上下文（RAG）。"""
from openai import OpenAI

from app.config import settings

# OpenAI 兼容客户端：base_url 指向 DeepSeek（或本地 vLLM）
client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY)

# 系统提示词：专业、克制、不使用 emoji
SYSTEM_PROMPT = (
    "你是一个专业的医疗健康咨询助手。请用简体中文回答。"
    "回答要简洁，用『-』开头、每项独立一行的列表输出，不要挤成长段落；"
    "只做健康咨询与就医指导，不能替代专业医疗诊断；"
    "禁止使用任何 emoji、表情符号；"
    "不要在回答中重复输出免责声明或安全提示（系统会统一附加）。"
)

# 有检索上下文时追加的约束：把「凭参数记忆作答」压成「依据证据作答」
GROUNDED_RULE = (
    "要求：回答必须以上述参考资料为依据，不要引入资料之外的具体事实"
    "（病名、药物、剂量、科室等）；"
    "资料未覆盖时直接说明知识库暂无相关内容，并建议就医确认。"
)


def build_messages(history: list, user_text: str, context: str = "", rules: str = "") -> list:
    """拼装消息列表。

    context 非空即为 RAG 模式：证据随 system 一起下发，并追加 grounded 约束；
    rules 是安全层按风险等级下发的硬性约束（急症/高危），优先级最高、放最后强调。
    """
    blocks = [SYSTEM_PROMPT]
    if context:
        blocks.append(context)
        blocks.append(GROUNDED_RULE)
    if rules:
        blocks.append(rules)
    msgs = [{"role": "system", "content": "\n\n".join(blocks)}]
    msgs.extend(history)
    msgs.append({"role": "user", "content": user_text})
    return msgs


def chat_once(history: list, user_text: str, context: str = "", rules: str = "",
              temperature: float | None = None) -> str:
    """非流式：一次返回完整回复。

    temperature 为 None 时用服务端默认（生产环境要自然度）；
    评估场景应显式传 0，否则同一用例两次跑分可能不同，指标不可复现。
    """
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=build_messages(history, user_text, context, rules),
        **kwargs,
    )
    return resp.choices[0].message.content or ""


def chat_stream(history: list, user_text: str, context: str = "", rules: str = ""):
    """流式生成器：逐块 yield 文本，用于 SSE。"""
    stream = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=build_messages(history, user_text, context, rules),
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
