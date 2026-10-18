"""Kernel：durable 状态内核门面，实现 LoopX 对齐的五原语。

五原语（对齐 LoopX / PRD §6.1）：
- should_run   该 agent 现在该不该跑？（依赖/配额/人工门）
- claim        认领当前工作切片（原子，写所有权租约）
- update       执行后写回结果与证据（受状态机硬约束）
- refresh_state 准备下一 turn 上下文（只注入必要状态，防长上下文膨胀）
- spend_slot   验证通过后消耗配额（限流/预算控制）

额外提供断点续跑（checkpoint / restore_from_checkpoint）与经验沉淀。
"""
from __future__ import annotations

from typing import List, Optional

from .models import (
    Checkpoint,
    Evidence,
    Experience,
    Goal,
    GoalStatus,
    Phase,
    ShouldRunResult,
    StateSnapshot,
    Todo,
    TodoStatus,
)
from .state_machine import (
    InvalidTransition,
    assert_transition,
    dependencies_satisfied,
    is_terminal_goal,
)
from .store import SQLiteStore, now


class Kernel:
    def __init__(self, db_path: str):
        self.store = SQLiteStore(db_path)

    def close(self) -> None:
        self.store.close()

    # ==================================================================
    # Goal / Todo 便捷创建
    # ==================================================================
    def create_goal(self, title: str, description: str = "",
                    scope: Optional[List[str]] = None,
                    workflow_id: str = "",
                    quota_total: int = 0,
                    goal_id: Optional[str] = None) -> Goal:
        return self.store.create_goal(
            title, description, scope, workflow_id, quota_total, goal_id)

    def create_todo(self, goal_id: str, file_path: str, phase: str,
                    dependencies: Optional[List[str]] = None,
                    max_attempts: int = 3,
                    todo_id: Optional[str] = None) -> Todo:
        return self.store.create_todo(
            goal_id, file_path, phase, dependencies, max_attempts, todo_id)

    # ==================================================================
    # 五原语
    # ==================================================================
    def should_run(self, goal_id: str, agent_id: Optional[str] = None) -> ShouldRunResult:
        """该 agent 现在该不该跑。"""
        goal = self.store.get_goal(goal_id)
        if goal is None:
            return ShouldRunResult(False, "goal 不存在")
        if is_terminal_goal(goal.status):
            return ShouldRunResult(False, f"goal 已终态: {goal.status}")
        if goal.status == GoalStatus.WAITING_GATE:
            return ShouldRunResult(False, "goal 处于人工门后，等待人工通过")
        if goal.status == GoalStatus.PAUSED:
            return ShouldRunResult(False, "goal 已暂停")
        if goal.quota_total > 0 and goal.quota_used >= goal.quota_total:
            return ShouldRunResult(False, "配额已耗尽")
        # 是否存在可认领的 ready 切片
        next_todo = self._find_next_ready(goal_id)
        if next_todo is None:
            # 无 ready：可能是全部 done（应由 update 推导 goal done），或有 blocked
            return ShouldRunResult(False, "无就绪切片可认领")
        return ShouldRunResult(True, "ok")

    def claim(self, goal_id: str, agent_id: str,
              todo_id: Optional[str] = None,
              lease_seconds: float = 300.0) -> Optional[Todo]:
        """认领切片。指定 todo_id 时认领该切片；否则按依赖取下一个就绪切片。"""
        goal = self.store.get_goal(goal_id)
        if goal is None or goal.status not in (GoalStatus.PLANNING, GoalStatus.RUNNING):
            return None
        if todo_id is not None:
            todo = self.store.get_todo(todo_id)
            if todo is None or todo.goal_id != goal_id:
                return None
            if todo.status != TodoStatus.READY:
                return None
            if not dependencies_satisfied(todo.dependencies, self._status_map(goal_id)):
                return None
            target = todo
        else:
            target = self._find_next_ready(goal_id)
            if target is None:
                return None
        # 原子认领
        ok = self.store.claim_todo(target.id, agent_id, lease_seconds)
        if not ok:
            return None
        # 认领后 goal 进入 running
        if goal.status == GoalStatus.PLANNING:
            self.store.set_goal_status(goal_id, GoalStatus.RUNNING)
        return self.store.get_todo(target.id)

    def update(self, todo_id: str, status: str, *,
               agent_id: Optional[str] = None,
               score: Optional[float] = None,
               artifacts: Optional[List[str]] = None,
               notes: str = "",
               error: Optional[str] = None) -> Todo:
        """执行后写回。受状态机硬约束，非法迁移抛 InvalidTransition。"""
        todo = self.store.get_todo(todo_id)
        if todo is None:
            raise KeyError(f"todo 不存在: {todo_id}")

        # 状态机硬约束
        assert_transition(todo.status, status, kind="todo")

        # 写证据
        if agent_id is not None or score is not None or artifacts is not None or notes:
            self.store.add_evidence(todo_id, agent_id, score, artifacts, notes)

        # 更新 todo 字段
        fields = {"status": status, "score": score, "error": error}
        if agent_id is not None:
            fields["owner_agent"] = agent_id
        if status == TodoStatus.DONE:
            fields["lease_expires_at"] = None
        updated = self.store.update_todo(todo_id, **fields)

        # failed：attempts++，未超限则回 ready（回环重试）
        if status == TodoStatus.FAILED:
            attempts = todo.attempts + 1
            if attempts < todo.max_attempts:
                self.store.update_todo(
                    todo_id, attempts=attempts, status=TodoStatus.READY,
                    owner_agent=None, lease_expires_at=None)
            else:
                self.store.update_todo(todo_id, attempts=attempts)
        # blocked：写断点后不自动回 ready（由退避/续跑逻辑处理）
        elif status == TodoStatus.BLOCKED:
            self.store.update_todo(todo_id, attempts=todo.attempts)

        self._maybe_advance_goal(todo.goal_id)
        return self.store.get_todo(todo_id)  # type: ignore[return-value]

    def refresh_state(self, goal_id: str,
                      agent_id: Optional[str] = None) -> StateSnapshot:
        """准备下一 turn 的上下文（只注入必要状态）。"""
        goal = self.store.get_goal(goal_id)
        todos = self.store.list_todos(goal_id)
        by_status = {TodoStatus.READY: 0, TodoStatus.CLAIMED: 0, TodoStatus.DONE: 0,
                     TodoStatus.BLOCKED: 0, TodoStatus.FAILED: 0}
        claimed: List[Todo] = []
        for t in todos:
            by_status[t.status] = by_status.get(t.status, 0) + 1
            if t.status == TodoStatus.CLAIMED:
                claimed.append(t)
        next_todo = self._find_next_ready(goal_id)
        open_gates = [g for g in self.store.list_gates(goal_id)
                      if g.status != "passed"]
        latest_cp = self.store.latest_checkpoint(goal_id)

        related = self._related_experiences(next_todo)

        return StateSnapshot(
            goal=goal,
            claimed_todos=claimed,
            next_todo=next_todo,
            progress={"done": by_status[TodoStatus.DONE],
                      "total": len(todos),
                      "failed": by_status[TodoStatus.FAILED],
                      "blocked": by_status[TodoStatus.BLOCKED],
                      "ready": by_status[TodoStatus.READY],
                      "claimed": by_status[TodoStatus.CLAIMED]},
            open_gates=open_gates,
            latest_checkpoint=latest_cp,
            related_experiences=related,
        )

    def spend_slot(self, goal_id: str, n: int = 1) -> bool:
        """验证通过后消耗配额。"""
        return self.store.spend_quota(goal_id, n)

    # ==================================================================
    # 断点续跑
    # ==================================================================
    def checkpoint(self, goal_id: str, todo_id: Optional[str],
                   state: dict) -> Checkpoint:
        return self.store.save_checkpoint(goal_id, todo_id, state)

    def restore_from_checkpoint(self, goal_id: str) -> Optional[dict]:
        """从最近 checkpoint 恢复状态（回放）。"""
        cp = self.store.latest_checkpoint(goal_id)
        return cp.state if cp else None

    # ==================================================================
    # 经验沉淀
    # ==================================================================
    def add_experience(self, category: str, trigger: str, solution: str,
                       versions: Optional[str] = None) -> Experience:
        return self.store.add_experience(category, trigger, solution, versions)

    def hit_experience(self, exp_id: str) -> None:
        self.store.hit_experience(exp_id)

    def search_experience(self, category: Optional[str] = None,
                          keyword: Optional[str] = None) -> List[Experience]:
        """检索经验（StateKernel 协议的一部分）。"""
        return self.store.search_experience(category=category, keyword=keyword)

    # ==================================================================
    # 内部
    # ==================================================================
    def _status_map(self, goal_id: str) -> dict:
        return {t.id: t.status for t in self.store.list_todos(goal_id)}

    def _find_next_ready(self, goal_id: str) -> Optional[Todo]:
        """按依赖图取下一个「依赖已满足且 status=ready」的切片。"""
        todos = self.store.list_todos(goal_id)
        status_by_id = {t.id: t.status for t in todos}
        for t in todos:  # 已按 created_at 排序，确定性取最早
            if t.status != TodoStatus.READY:
                continue
            if dependencies_satisfied(t.dependencies, status_by_id):
                return t
        return None

    def _related_experiences(self, next_todo: Optional[Todo]) -> List[Experience]:
        if next_todo is None:
            return []
        # 按 phase 类别命中经验（后续 M6 可扩展为关键词向量匹配）
        phase = next_todo.phase
        return self.store.search_experience(category=phase)

    def _maybe_advance_goal(self, goal_id: str) -> None:
        """当所有 todo 完成时推导 goal 终态。"""
        goal = self.store.get_goal(goal_id)
        if goal is None or is_terminal_goal(goal.status):
            return
        todos = self.store.list_todos(goal_id)
        if not todos:
            return
        if all(t.status == TodoStatus.DONE for t in todos):
            open_gates = [g for g in self.store.list_gates(goal_id)
                          if g.status != "passed"]
            if open_gates:
                self.store.set_goal_status(goal_id, GoalStatus.WAITING_GATE)
            else:
                self.store.set_goal_status(goal_id, GoalStatus.DONE)
