"""指数退避 + jitter（PRD §7：API 限流自动退避重试）。"""
from __future__ import annotations

import random


class BackoffStrategy:
    """指数退避：delay(attempt) = min(base * factor^attempt, max) * jitter。"""

    def __init__(self, base_seconds: float = 1.0, max_seconds: float = 60.0,
                 factor: float = 2.0, jitter: float = 0.1,
                 rng: random.Random | None = None):
        if base_seconds <= 0 or max_seconds < base_seconds or factor < 1.0:
            raise ValueError("退避参数非法：需 base>0, max>=base, factor>=1")
        if not (0.0 <= jitter < 1.0):
            raise ValueError("jitter 需在 [0,1) 内")
        self.base = float(base_seconds)
        self.max = float(max_seconds)
        self.factor = float(factor)
        self.jitter = float(jitter)
        self._rng = rng or random.Random()

    def delay(self, attempt: int) -> float:
        """第 attempt 次重试（从 0 起）应等待的秒数。"""
        raw = self.base * (self.factor ** max(0, attempt))
        raw = min(raw, self.max)
        if self.jitter > 0:
            raw *= self._rng.uniform(1.0 - self.jitter, 1.0 + self.jitter)
        return max(0.0, raw)

    def delays(self, attempts: int) -> list:
        """前 attempts 次重试的等待序列。"""
        return [self.delay(i) for i in range(attempts)]
