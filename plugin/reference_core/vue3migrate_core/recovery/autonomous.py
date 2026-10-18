"""自愈循环：把退避 + 异常分类 + checkpoint 接进调度循环。

对齐 PRD §7 自愈循环伪代码：
    while not done:
        node = claim_next()
        result = agent.run(node.slice)
        if rate_limited: backoff(); continue
        if truncated:    checkpoint(); continue   # 断点续跑
        score = quality_gate(...)
        if score < threshold: fix; continue        # 回环修复
        mark_done()

`autonomous_run` 提供带自愈的完整调度循环，可注入 sleep_fn 供测试。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..engine import ExecutionResult, Node, Scheduler
from .backoff import BackoffStrategy
from .checkpointing import JsonCheckpointStore
from .errors import classify
from .policy import RecoveryAction, RecoveryPolicy


@dataclass
class RecoveryEvent:
    node_id: str
    action: str
    category: str
    attempt: int
    delay_seconds: float
    message: str


@dataclass
class AutonomousReport:
    done: bool
    trace: List[str]
    states: dict
    failed_nodes: List[str]
    events: List[RecoveryEvent]
    checkpointed: int
    reason: str


def autonomous_run(
    sched: Scheduler,
    runner: Callable[[Node, dict], ExecutionResult],
    policy: Optional[RecoveryPolicy] = None,
    backoff: Optional[BackoffStrategy] = None,
    store: Optional[JsonCheckpointStore] = None,
    workflow_id: str = "wf",
    sleep_fn: Callable[[float], None] = time.sleep,
    max_ticks: int = 1000,
    checkpoint_every: bool = True,
) -> AutonomousReport:
    """驱动 DAG 直到完成或无法推进，并在异常时按策略自愈。

    - runner 返回 truncated=True → BLOCK（写 checkpoint 后阻塞）。
    - runner 返回 success=False → classify(error) → policy.decide：
        * BACKOFF：按退避等待后重试
        * RETRY：引擎 fail() 回环
        * RECOVER_DEPENDENCY：回退（引擎 fail() 回环，配合 deps 阶段）
        * MANUAL：引擎 fail() 至 FAILED
    - 每轮 tick 后可选 checkpoint（断点续跑）。
    """
    policy = policy or RecoveryPolicy()
    backoff = backoff or BackoffStrategy()
    events: List[RecoveryEvent] = []
    checkpointed = 0
    ticks = 0

    def _save() -> None:
        nonlocal checkpointed
        if store is not None:
            store.save(workflow_id, sched)
            checkpointed += 1

    while ticks < max_ticks:
        if sched.is_done():
            break
        node = sched.next()
        if node is None:
            if sched.is_stuck():
                _save()
                break
            # 串行占用中：正常情况不 sleep，直接返回由调用方再 tick
            break

        result = runner(node, sched.build_slice(node))

        if result.truncated:
            sched.block(node.id)
            category = classify("truncated")
            events.append(RecoveryEvent(node.id, RecoveryAction.BLOCK.value,
                                        category.value, sched.attempts(node.id),
                                        0.0, "截断，写 checkpoint 待续跑"))
            _save()
            continue

        if result.success:
            sched.complete(node.id)
            if checkpoint_every:
                _save()
            ticks += 1
            continue

        # 失败 → 分类 → 策略
        category = classify(result.error)
        attempt = sched.attempts(node.id)
        decision = policy.decide(category, attempt,
                                 backoff_delay=backoff.delay(attempt))

        if decision.action is RecoveryAction.BACKOFF:
            sleep_fn(decision.delay_seconds)
            # 退避后重试：fail() 递增 attempts，使下一次退避更长（指数退避），
            # 且连续限流达到 max_attempts 后 FAILED（升级人工门）。
            sched.fail(node.id, result.error)
            events.append(RecoveryEvent(node.id, decision.action.value,
                                        category.value, attempt,
                                        decision.delay_seconds, decision.message))
            _save()
            ticks += 1
            continue

        if decision.action is RecoveryAction.RECOVER_DEPENDENCY:
            # 依赖缺失：fail 回环（配合 deps 阶段重新分析）
            sched.fail(node.id, result.error)
            events.append(RecoveryEvent(node.id, decision.action.value,
                                        category.value, attempt,
                                        0.0, decision.message))
            _save()
            ticks += 1
            continue

        # RETRY / MANUAL：交给引擎 fail()（超限自动 FAILED=人工门）
        sched.fail(node.id, result.error)
        events.append(RecoveryEvent(node.id, decision.action.value,
                                    category.value, attempt,
                                    0.0, decision.message))
        _save()
        ticks += 1

    done = sched.is_done()
    reason = "完成" if done else (
        "卡住：存在 blocked/failed 或依赖未满足" if sched.is_stuck() else "未完成")
    return AutonomousReport(
        done=done, trace=list(sched._trace), states=sched.states(),
        failed_nodes=sched.failed_nodes(), events=events,
        checkpointed=checkpointed, reason=reason)
