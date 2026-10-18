"""StateKernel 协议：自研 SQLite 内核与 LoopX 内核的统一抽象接口。

五原语（对齐 LoopX）：
- should_run     该 agent 现在该不该跑？
- claim          原子认领当前工作切片
- update         执行后写回结果与证据（受状态机硬约束）
- refresh_state  准备下一 turn 上下文（只注入必要状态）
- spend_slot     验证通过后消耗配额

通过本 Protocol，上层（DAG 引擎 / 插件工具 / CLI）无需关心底层是
SQLite 自研内核还是 LoopX 内核——两者可互换（`create_kernel` 工厂切换）。
"""
from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from .models import (
    Checkpoint,
    Experience,
    Goal,
    ShouldRunResult,
    StateSnapshot,
    Todo,
)


@runtime_checkable
class StateKernel(Protocol):
    """durable 状态内核的最小协议面。"""

    # ---- Goal / Todo 创建 ----
    def create_goal(self, title: str, description: str = "",
                    scope: Optional[List[str]] = None,
                    workflow_id: str = "",
                    quota_total: int = 0,
                    goal_id: Optional[str] = None) -> Goal: ...

    def create_todo(self, goal_id: str, file_path: str, phase: str,
                    dependencies: Optional[List[str]] = None,
                    max_attempts: int = 3,
                    todo_id: Optional[str] = None) -> Todo: ...

    # ---- 五原语 ----
    def should_run(self, goal_id: str,
                   agent_id: Optional[str] = None) -> ShouldRunResult: ...

    def claim(self, goal_id: str, agent_id: str,
              todo_id: Optional[str] = None,
              lease_seconds: float = 300.0) -> Optional[Todo]: ...

    def update(self, todo_id: str, status: str, *,
               agent_id: Optional[str] = None,
               score: Optional[float] = None,
               artifacts: Optional[List[str]] = None,
               notes: str = "",
               error: Optional[str] = None) -> Todo: ...

    def refresh_state(self, goal_id: str,
                      agent_id: Optional[str] = None) -> StateSnapshot: ...

    def spend_slot(self, goal_id: str, n: int = 1) -> bool: ...

    # ---- 断点续跑 ----
    def checkpoint(self, goal_id: str, todo_id: Optional[str],
                   state: dict) -> Checkpoint: ...

    def restore_from_checkpoint(self, goal_id: str) -> Optional[dict]: ...

    # ---- 经验沉淀 ----
    def add_experience(self, category: str, trigger: str, solution: str,
                       versions: Optional[str] = None) -> Experience: ...

    def hit_experience(self, exp_id: str) -> None: ...

    def search_experience(self, category: Optional[str] = None,
                          keyword: Optional[str] = None) -> List[Experience]: ...

    # ---- 生命周期 ----
    def close(self) -> None: ...


__all__ = ["StateKernel"]
