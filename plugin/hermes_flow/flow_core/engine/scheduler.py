"""调度器：串行硬约束的 DAG 调度循环。

核心设计（直击用户痛点——长上下文注意力衰退导致违反串行约束）：
- **串行是硬约束**：默认一次只允许一个节点 running，违规并行在 `next()` 处被拒绝。
- 仅当节点显式声明 `parallel=True` 时才允许并发，且非 parallel 节点运行时独占。
- **单 turn 切片上下文**：`build_slice` 只注入当前节点 + 依赖完成摘要，不累积历史，
  从根上避免上下文膨胀。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .dag import Node, Workflow, topological_sort

# 节点运行时状态
READY = "ready"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
BLOCKED = "blocked"


@dataclass
class ExecutionResult:
    """runner 的执行结果。"""
    success: bool
    score: Optional[float] = None
    artifacts: List[str] = field(default_factory=list)
    notes: str = ""
    error: Optional[str] = None
    truncated: bool = False      # 上下文截断 → 触发断点续跑（blocked）


@dataclass
class TickResult:
    """单次 tick 的结果。"""
    progressed: bool
    node_id: Optional[str]
    reason: str


@dataclass
class RunReport:
    done: bool
    trace: List[str]                       # 节点 id 按实际执行顺序
    states: Dict[str, str]
    ticks: int
    reason: str
    failed_nodes: List[str] = field(default_factory=list)


class Scheduler:
    def __init__(self, workflow: Workflow, max_attempts: int = 3):
        self.workflow = workflow
        self.max_attempts = max_attempts
        # 构造时即校验 DAG 合法性（环检测），非法图直接拒绝
        topological_sort(workflow)
        self._status: Dict[str, str] = {n.id: READY for n in workflow.nodes}
        self._attempts: Dict[str, int] = {n.id: 0 for n in workflow.nodes}
        self._trace: List[str] = []

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def status(self, node_id: str) -> str:
        return self._status[node_id]

    def attempts(self, node_id: str) -> int:
        """该节点已失败的次数（回环计数）。"""
        return self._attempts[node_id]

    # ------------------------------------------------------------------
    # 快照 / 恢复（跨会话持久化，供 recovery 层使用）
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """把当前调度状态序列化为 dict，可跨会话持久化。"""
        return {
            "workflow": self.workflow.to_dict(),
            "status": dict(self._status),
            "attempts": dict(self._attempts),
            "trace": list(self._trace),
            "max_attempts": self.max_attempts,
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> "Scheduler":
        """从 snapshot 恢复调度器（断点续跑）。"""
        wf = Workflow.from_dict(data["workflow"])
        sched = cls(wf, max_attempts=data.get("max_attempts", 3))
        sched._status = dict(data.get("status", {}))
        sched._attempts = dict(data.get("attempts", {}))
        sched._trace = list(data.get("trace", []))
        return sched

    def states(self) -> Dict[str, str]:
        return dict(self._status)

    def running_nodes(self) -> List[Node]:
        return [n for n in self.workflow.nodes if self._status[n.id] == RUNNING]

    def ready_nodes(self) -> List[Node]:
        """依赖全部 done 且自身 ready 的节点，按拓扑序返回。"""
        order = topological_sort(self.workflow)
        result: List[Node] = []
        for nid in order:
            if self._status[nid] != READY:
                continue
            node = self.workflow.node(nid)
            if all(self._status[p] == DONE
                   for p in self.workflow.predecessors(nid)):
                result.append(node)
        return result

    def is_done(self) -> bool:
        return all(s == DONE for s in self._status.values())

    def failed_nodes(self) -> List[str]:
        return [nid for nid, s in self._status.items() if s == FAILED]

    def is_stuck(self) -> bool:
        """无法继续推进：无 ready、无 running，但仍存在非终态节点。"""
        if self.is_done():
            return False
        if self.running_nodes():
            return False
        return not self.ready_nodes()

    # ------------------------------------------------------------------
    # 核心：串行硬约束的 next()
    # ------------------------------------------------------------------
    def next(self) -> Optional[Node]:
        """返回下一个该执行的节点，并标记为 running。

        串行硬约束：若已有 running 节点，且其中存在非 parallel 节点，则拒绝放行
        新节点（返回 None）。仅当所有 running 节点都是 parallel 时，才允许再放行
        一个 parallel 节点。
        """
        running = self.running_nodes()
        if running:
            if any(not n.parallel for n in running):
                return None  # 非 parallel 节点独占 → 违规并行被拒绝
            ready = [n for n in self.ready_nodes() if n.parallel]
            if not ready:
                return None
        else:
            ready = self.ready_nodes()
            if not ready:
                return None
        node = ready[0]
        self._status[node.id] = RUNNING
        self._trace.append(node.id)
        return node

    # ------------------------------------------------------------------
    # 状态推进
    # ------------------------------------------------------------------
    def complete(self, node_id: str) -> None:
        self._status[node_id] = DONE

    def fail(self, node_id: str, error: Optional[str] = None) -> None:
        self._attempts[node_id] += 1
        if self._attempts[node_id] < self.max_attempts:
            self._status[node_id] = READY   # 回环重试
        else:
            self._status[node_id] = FAILED

    def block(self, node_id: str) -> None:
        """限流/截断 → 阻塞（等待退避后续跑）。"""
        self._status[node_id] = BLOCKED

    def unblock(self, node_id: str) -> None:
        self._status[node_id] = READY

    # ------------------------------------------------------------------
    # 切片上下文（防上下文膨胀）
    # ------------------------------------------------------------------
    def build_slice(self, node: Node) -> dict:
        """单 turn 只注入当前节点 + 依赖完成摘要。"""
        return {
            "node": {
                "id": node.id, "name": node.name, "phase": node.phase,
                "agent": node.agent, "skill": node.skill, "meta": node.meta,
            },
            "dependencies_done": [
                p for p in self.workflow.predecessors(node.id)
                if self._status[p] == DONE
            ],
            "attempt": self._attempts[node.id],
        }

    # ------------------------------------------------------------------
    # 调度循环
    # ------------------------------------------------------------------
    def tick(self, runner: Callable[[Node, dict], ExecutionResult]) -> TickResult:
        """推进一步：next → runner 执行 → 按结果 complete/fail/block。"""
        if self.is_done():
            return TickResult(False, None, "所有节点已完成")
        node = self.next()
        if node is None:
            if self.is_stuck():
                return TickResult(False, None,
                                  "卡住：无就绪节点（blocked/failed 或依赖未满足）")
            return TickResult(False, None, "串行占用中（当前节点运行中）")
        result = runner(node, self.build_slice(node))
        if result.truncated:
            self.block(node.id)
            return TickResult(True, node.id, "截断，已阻塞等待续跑")
        if result.success:
            self.complete(node.id)
            return TickResult(True, node.id, "完成")
        self.fail(node.id, result.error)
        return TickResult(True, node.id, f"失败（第 {self._attempts[node.id]} 次）")

    def run(self, runner: Callable[[Node, dict], ExecutionResult],
            max_ticks: int = 1000) -> RunReport:
        """驱动整个 DAG 直到完成或无法推进。"""
        ticks = 0
        while ticks < max_ticks:
            if self.is_done():
                break
            ticks += 1
            r = self.tick(runner)
            if not r.progressed:
                break  # 串行占用 or stuck
        done = self.is_done()
        reason = "完成" if done else (
            "卡住：存在 blocked/failed 或依赖未满足" if self.is_stuck() else "未完成")
        return RunReport(
            done=done, trace=list(self._trace), states=self.states(),
            ticks=ticks, reason=reason, failed_nodes=self.failed_nodes(),
        )
