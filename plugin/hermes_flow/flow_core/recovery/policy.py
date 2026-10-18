"""恢复策略：异常类别 → 恢复动作（PRD §7 自愈循环）。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import FailureCategory


class RecoveryAction(str, Enum):
    RETRY = "retry"                          # 立即重试（引擎回环）
    BACKOFF = "backoff"                      # 退避后重试
    BLOCK = "block"                          # 写 checkpoint 后阻塞，等待续跑
    RECOVER_DEPENDENCY = "recover_dependency"  # 回退 deps 阶段重新分析
    MANUAL = "manual"                        # 升级人工门


@dataclass
class RecoveryDecision:
    action: RecoveryAction
    category: FailureCategory
    attempt: int
    delay_seconds: float = 0.0
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "category": self.category.value,
            "attempt": self.attempt,
            "delay_seconds": round(self.delay_seconds, 3),
            "message": self.message,
        }


# 类别 → 默认动作（对齐 PRD §7 异常表）
_DEFAULT_ACTIONS: dict = {
    FailureCategory.RATE_LIMIT: RecoveryAction.BACKOFF,
    FailureCategory.TRUNCATION: RecoveryAction.BLOCK,
    FailureCategory.TIMEOUT: RecoveryAction.RETRY,
    FailureCategory.DEPENDENCY_MISSING: RecoveryAction.RECOVER_DEPENDENCY,
    FailureCategory.COMPILE_ERROR: RecoveryAction.RETRY,
    FailureCategory.QUALITY_LOW: RecoveryAction.RETRY,
    FailureCategory.AGENT_DRIFT: RecoveryAction.RETRY,
    FailureCategory.DESTRUCTIVE: RecoveryAction.MANUAL,
    FailureCategory.UNKNOWN: RecoveryAction.RETRY,
}


class RecoveryPolicy:
    """类别 → 动作，且带重试上限（超限升级人工门）。"""

    def __init__(self, max_retries: int = 3, actions: dict | None = None):
        self.max_retries = max_retries
        self.actions = dict(_DEFAULT_ACTIONS)
        if actions:
            self.actions.update(actions)

    def decide(self, category: FailureCategory, attempt: int,
               backoff_delay: float = 0.0) -> RecoveryDecision:
        # 破坏性动作：无条件人工门
        if category is FailureCategory.DESTRUCTIVE:
            return RecoveryDecision(RecoveryAction.MANUAL, category, attempt,
                                    message="破坏性/发布动作，强制人工门")
        # 重试超限：升级人工门
        if attempt >= self.max_retries:
            return RecoveryDecision(
                RecoveryAction.MANUAL, category, attempt,
                message=f"重试已达上限 {self.max_retries} 次，升级人工门")
        action = self.actions.get(category, RecoveryAction.RETRY)
        msg = {
            RecoveryAction.BACKOFF: f"限流，退避 {backoff_delay:.1f}s 后重试",
            RecoveryAction.BLOCK: "截断，写 checkpoint 待续跑",
            RecoveryAction.RECOVER_DEPENDENCY: "依赖缺失，回退 deps 重新分析",
            RecoveryAction.RETRY: f"第 {attempt + 1}/{self.max_retries} 次重试",
        }.get(action, "")
        return RecoveryDecision(action, category, attempt,
                                delay_seconds=backoff_delay, message=msg)
