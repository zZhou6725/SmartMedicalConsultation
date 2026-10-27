"""熔断器：依赖外部服务时必须假设它会挂。

没有熔断时，LLM 不可用的表现是「每个请求都卡满超时再失败」——
并发上来会把工作线程全部拖死。熔断器的作用是：
连续失败达阈值后直接快速失败（抛 CircuitOpen），冷却一段时间再放一个请求去试探。

配合降级：调用方捕获 CircuitOpen 立即给出兜底答复，而不是干等。
"""
import threading
import time

from app.config import settings


class CircuitOpen(RuntimeError):
    """熔断打开：调用被直接拒绝，不发起真实请求。"""


class CircuitBreaker:
    """极简三态熔断器（closed → open → half-open）。"""

    def __init__(self, name: str, threshold: int | None = None,
                 cooldown: float | None = None):
        self.name = name
        self.threshold = threshold if threshold is not None else settings.LLM_BREAKER_THRESHOLD
        self.cooldown = cooldown if cooldown is not None else float(settings.LLM_BREAKER_COOLDOWN)
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = 0.0

    # ---- 状态 ----

    @property
    def state(self) -> str:
        with self._lock:
            if self._failures < self.threshold:
                return "closed"
            if time.time() - self._opened_at < self.cooldown:
                return "open"
            return "half-open"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": "open" if (self._failures >= self.threshold
                                    and time.time() - self._opened_at < self.cooldown)
                         else ("half-open" if self._failures >= self.threshold else "closed"),
                "failures": self._failures,
                "threshold": self.threshold,
                "cooldown": self.cooldown,
            }

    def reset(self):
        with self._lock:
            self._failures = 0
            self._opened_at = 0.0

    # ---- 调用 ----

    def call(self, fn, *args, **kwargs):
        """执行 fn；处于 open 状态时直接抛 CircuitOpen。"""
        with self._lock:
            if self._failures >= self.threshold:
                if time.time() - self._opened_at < self.cooldown:
                    raise CircuitOpen(
                        f"{self.name} 已熔断（连续失败 {self._failures} 次，"
                        f"冷却剩余 {int(self.cooldown - (time.time() - self._opened_at))}s）")
                # 冷却结束 → 半开，允许一次试探
                self._failures = self.threshold - 1

        try:
            result = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.threshold:
                    self._opened_at = time.time()
            raise
        else:
            with self._lock:
                self._failures = 0
            return result


# 全局实例：大模型调用
llm_breaker = CircuitBreaker("llm")
