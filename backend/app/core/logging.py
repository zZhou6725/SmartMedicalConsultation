"""结构化日志：JSON 输出 + trace_id 贯穿。

为什么不用 print：企业里日志要被采集、检索、按链路聚合。
自由文本日志无法按字段过滤（找不出「intent=drug 且耗时 > 5s 的请求」），
所以统一输出 JSON，并把当次请求的 trace_id 自动带上。

LOG_JSON=0 可切回人类可读格式（本地调试用）。
"""
import json
import logging
import sys
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")

# 允许附加到日志记录的上下文字段（只透传白名单，避免把大对象塞进日志）
_EXTRA_FIELDS = ("intent", "session_id", "latency_ms", "retrieve_ms",
                 "generate_ms", "fallback", "tool", "error", "status_code")


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id or "-")


def get_trace_id() -> str:
    return _trace_id.get()


class JsonFormatter(logging.Formatter):
    """把日志记录序列化成一行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "traceId": get_trace_id(),
        }
        for key in _EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)[:800]
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", json_mode: bool = True) -> None:
    """初始化根 logger（幂等，重复调用只会重置 handler）。"""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if json_mode:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s  %(message)s"))
    root.addHandler(handler)
    root.setLevel((level or "INFO").upper())

    # 第三方库的噪音压到 WARNING
    for noisy in ("neo4j", "httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
