"""状态机：受治理的状态转换（引擎硬约束的核心）。

「串行是引擎硬约束，不是 prompt 软约束」——本模块用显式转换矩阵保证任何
非法状态迁移（例如 ready 直接跳 done、claimed 并发写 done 后再乱跳）都被拒绝。
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, Mapping, Optional

from .models import GoalStatus, TodoStatus

# ---------------------------------------------------------------------------
# 合法转换矩阵
# ---------------------------------------------------------------------------
# ready ──claim──▶ claimed ──update──▶ done ──gate──▶ passed
#   │               │ ▲
#   │               │ └── failed(attempts<max) ──▶ ready
#   │               └── 限流/截断 ──▶ blocked ──退避──▶ ready
#   └── 依赖未满足 ──▶ blocked
TODO_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    TodoStatus.READY:    frozenset({TodoStatus.CLAIMED, TodoStatus.BLOCKED}),
    TodoStatus.CLAIMED:  frozenset({TodoStatus.DONE, TodoStatus.BLOCKED, TodoStatus.FAILED, TodoStatus.READY}),
    TodoStatus.BLOCKED:  frozenset({TodoStatus.READY, TodoStatus.CLAIMED}),
    TodoStatus.FAILED:   frozenset({TodoStatus.READY}),
    TodoStatus.DONE:     frozenset(),  # 终态
}

GOAL_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    GoalStatus.PLANNING:     frozenset({GoalStatus.RUNNING, GoalStatus.PAUSED, GoalStatus.FAILED}),
    GoalStatus.RUNNING:      frozenset({GoalStatus.WAITING_GATE, GoalStatus.PAUSED, GoalStatus.DONE, GoalStatus.FAILED}),
    GoalStatus.WAITING_GATE: frozenset({GoalStatus.RUNNING, GoalStatus.DONE, GoalStatus.PAUSED, GoalStatus.FAILED}),
    GoalStatus.PAUSED:       frozenset({GoalStatus.RUNNING, GoalStatus.FAILED}),
    GoalStatus.DONE:         frozenset(),
    GoalStatus.FAILED:       frozenset(),
}

# 终态集合
TODO_TERMINAL = frozenset({TodoStatus.DONE})
GOAL_TERMINAL = frozenset({GoalStatus.DONE, GoalStatus.FAILED})


class InvalidTransition(ValueError):
    """非法状态迁移异常。"""


def can_transition(current: str, target: str, table: Mapping[str, Iterable[str]]) -> bool:
    """判断 current -> target 是否合法。"""
    return current == target or target in table.get(current, frozenset())


def assert_transition(current: str, target: str, kind: str = "todo") -> None:
    """断言迁移合法，否则抛 InvalidTransition。"""
    table = TODO_TRANSITIONS if kind == "todo" else GOAL_TRANSITIONS
    if not can_transition(current, target, table):
        raise InvalidTransition(
            f"非法{kind}状态迁移: {current!r} -> {target!r}"
        )


def dependencies_satisfied(dep_ids: Iterable[str], status_by_id: Mapping[str, str]) -> bool:
    """依赖是否全部完成（status == done）。"""
    for dep in dep_ids:
        if status_by_id.get(dep) != TodoStatus.DONE:
            return False
    return True


def is_terminal_todo(status: str) -> bool:
    return status in TODO_TERMINAL


def is_terminal_goal(status: str) -> bool:
    return status in GOAL_TERMINAL
