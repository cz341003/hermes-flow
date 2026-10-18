"""LoopX 适配器：让自研 SQLite 内核可切换到 LoopX 风格的状态内核。

设计目标（对齐 PRD §6.1 / 实现计划「五原语接口抽象」）：
- 自研 SQLite 内核（``Kernel``）与 LoopX 内核（``LoopXKernel``）可互换，
  都实现 :class:`StateKernel` 协议，上层（DAG 引擎 / 插件工具 / CLI）无感知。
- ``LoopXKernel`` 采用 JSONL **domain-state ledger** 后端，文件布局与稳定键
  upsert 语义对齐 LoopX 的 ``.loopx/domain-state/`` 设计——不依赖本地安装
  LoopX wheel 也能完整运行，未来可无缝替换为真正的 LoopX CLI 后端。
- ``LoopXBridge`` 是 CLI 桥接点，封装 ``loopx`` 真实 CLI 的调用（未安装时
  抛出清晰错误），作为切换到真实 LoopX 的升级路径。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ..kernel.models import (
    Checkpoint,
    Experience,
    Gate,
    GateStatus,
    Goal,
    GoalStatus,
    ShouldRunResult,
    StateSnapshot,
    Todo,
    TodoStatus,
)
from ..kernel.state_machine import (
    assert_transition,
    dependencies_satisfied,
    is_terminal_goal,
)
from ..kernel.store import now, uid

try:
    import fcntl  # POSIX
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore


# ---------------------------------------------------------------------------
# 跨进程文件锁（Windows 用 msvcrt，POSIX 用 fcntl）
# ---------------------------------------------------------------------------
class _FileLock:
    def __init__(self, path: str):
        self._path = path
        self._fh = None

    def __enter__(self):
        self._fh = open(self._path, "a+")
        if fcntl is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        else:
            import msvcrt
            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)
        return self

    def __exit__(self, *exc):
        if fcntl is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        else:
            import msvcrt
            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        self._fh.close()
        self._fh = None


# ---------------------------------------------------------------------------
# JSONL domain-state ledger（对齐 LoopX 的 upsert_domain_state_jsonl 语义）
# ---------------------------------------------------------------------------
class _JsonlLedger:
    """每行一个实体，按 ``domain_state_key`` 稳定键 upsert。"""

    def __init__(self, path: str):
        self.path = path

    def _read_rows(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        rows: List[Dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSONL row in {self.path}") from exc
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    def _write_rows(self, rows: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with _FileLock(self.path + ".lock"):
            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(self.path), prefix=".tmp.", suffix=".jsonl")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    for row in rows:
                        f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    def upsert(self, key: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        """按稳定键 upsert 一行，返回写入后的行。"""
        rows = self._read_rows()
        candidate = {**payload, "domain_state_key": key}
        updated = False
        for i, row in enumerate(rows):
            if row.get("domain_state_key") == key:
                rows[i] = candidate
                updated = True
                break
        if not updated:
            rows.append(candidate)
        self._write_rows(rows)
        return candidate

    def read(self, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for row in self._read_rows():
            if row.get("domain_state_key") == key:
                return row
        return None

    def read_all(self, type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for row in self._read_rows():
            if type_filter is None or row.get("domain_state_key", {}).get("type") == type_filter:
                out.append(row)
        return out

    def drop(self, key: Dict[str, Any]) -> None:
        rows = [r for r in self._read_rows() if r.get("domain_state_key") != key]
        self._write_rows(rows)

    def drop_all(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)


# ---------------------------------------------------------------------------
# LoopXKernel：JSONL domain-state 后端实现 StateKernel
# ---------------------------------------------------------------------------
class LoopXKernel:
    """LoopX 风格内核（JSONL domain-state ledger），与 SQLite ``Kernel`` 等价。"""

    def __init__(self, root: str):
        self.root = os.path.abspath(os.path.expanduser(root))
        self._lock = threading.RLock()

    # ---- 路径 ----
    def _goal_ledger(self, goal_id: str) -> _JsonlLedger:
        return _JsonlLedger(os.path.join(
            self.root, ".loopx", "domain-state", goal_id, f"{goal_id}.jsonl"))

    def _exp_ledger(self) -> _JsonlLedger:
        return _JsonlLedger(os.path.join(self.root, ".loopx", "experience.jsonl"))

    # ---- Goal / Todo 创建 ----
    def create_goal(self, title: str, description: str = "",
                    scope: Optional[List[str]] = None,
                    workflow_id: str = "",
                    quota_total: int = 0,
                    goal_id: Optional[str] = None) -> Goal:
        gid = goal_id or uid("goal")
        goal = Goal(id=gid, title=title, description=description,
                    scope=scope or [], workflow_id=workflow_id,
                    quota_total=quota_total, status=GoalStatus.PLANNING,
                    created_at=now(), updated_at=now())
        with self._lock:
            self._goal_ledger(gid).upsert(
                {"type": "goal", "id": gid}, asdict(goal))
        return goal

    def create_todo(self, goal_id: str, file_path: str, phase: str,
                    dependencies: Optional[List[str]] = None,
                    max_attempts: int = 3,
                    todo_id: Optional[str] = None) -> Todo:
        tid = todo_id or uid("todo")
        todo = Todo(id=tid, goal_id=goal_id, file_path=file_path, phase=phase,
                    dependencies=dependencies or [], max_attempts=max_attempts,
                    status=TodoStatus.READY, created_at=now(), updated_at=now())
        with self._lock:
            self._goal_ledger(goal_id).upsert(
                {"type": "todo", "id": tid}, asdict(todo))
        return todo

    # ---- 内部读 ----
    def _get_goal(self, goal_id: str) -> Optional[Goal]:
        row = self._goal_ledger(goal_id).read({"type": "goal", "id": goal_id})
        return Goal(**{k: v for k, v in row.items() if k != "domain_state_key"}) if row else None

    def _get_todo(self, todo_id: str) -> Optional[Todo]:
        for ledger in self._all_ledgers():
            row = ledger.read({"type": "todo", "id": todo_id})
            if row:
                return Todo(**{k: v for k, v in row.items() if k != "domain_state_key"})
        return None

    def _list_todos(self, goal_id: str) -> List[Todo]:
        rows = self._goal_ledger(goal_id).read_all("todo")
        out = []
        for row in rows:
            out.append(Todo(**{k: v for k, v in row.items() if k != "domain_state_key"}))
        out.sort(key=lambda t: t.created_at)
        return out

    def _all_ledgers(self) -> List[_JsonlLedger]:
        base = os.path.join(self.root, ".loopx", "domain-state")
        ledgers = []
        if os.path.isdir(base):
            for gid in os.listdir(base):
                ledgers.append(self._goal_ledger(gid))
        return ledgers

    def _set_goal_status(self, goal_id: str, status: str) -> None:
        goal = self._get_goal(goal_id)
        if goal is None:
            return
        goal.status = status
        goal.updated_at = now()
        self._goal_ledger(goal_id).upsert({"type": "goal", "id": goal_id}, asdict(goal))

    # ---- 五原语 ----
    def should_run(self, goal_id: str,
                   agent_id: Optional[str] = None) -> ShouldRunResult:
        goal = self._get_goal(goal_id)
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
        if self._find_next_ready(goal_id) is None:
            return ShouldRunResult(False, "无就绪切片可认领")
        return ShouldRunResult(True, "ok")

    def claim(self, goal_id: str, agent_id: str,
              todo_id: Optional[str] = None,
              lease_seconds: float = 300.0) -> Optional[Todo]:
        with self._lock:
            goal = self._get_goal(goal_id)
            if goal is None or goal.status not in (GoalStatus.PLANNING, GoalStatus.RUNNING):
                return None
            target = None
            if todo_id is not None:
                todo = self._get_todo(todo_id)
                if (todo is None or todo.goal_id != goal_id
                        or todo.status != TodoStatus.READY):
                    return None
                if not dependencies_satisfied(todo.dependencies, self._status_map(goal_id)):
                    return None
                target = todo
            else:
                target = self._find_next_ready(goal_id)
                if target is None:
                    return None
            target.status = TodoStatus.CLAIMED
            target.owner_agent = agent_id
            target.lease_expires_at = now() + lease_seconds
            target.updated_at = now()
            self._goal_ledger(goal_id).upsert(
                {"type": "todo", "id": target.id}, asdict(target))
            if goal.status == GoalStatus.PLANNING:
                self._set_goal_status(goal_id, GoalStatus.RUNNING)
            return self._get_todo(target.id)

    def update(self, todo_id: str, status: str, *,
               agent_id: Optional[str] = None,
               score: Optional[float] = None,
               artifacts: Optional[List[str]] = None,
               notes: str = "",
               error: Optional[str] = None) -> Todo:
        todo = self._get_todo(todo_id)
        if todo is None:
            raise KeyError(f"todo 不存在: {todo_id}")
        assert_transition(todo.status, status, kind="todo")

        todo.status = status
        todo.score = score
        todo.error = error
        if agent_id is not None:
            todo.owner_agent = agent_id
        todo.updated_at = now()

        ledger = self._goal_ledger(todo.goal_id)
        with self._lock:
            if status == TodoStatus.DONE:
                todo.lease_expires_at = None
            elif status == TodoStatus.FAILED:
                todo.attempts += 1
                if todo.attempts < todo.max_attempts:
                    todo.status = TodoStatus.READY
                    todo.owner_agent = None
                    todo.lease_expires_at = None
            elif status == TodoStatus.BLOCKED:
                pass

            ledger.upsert({"type": "todo", "id": todo.id}, asdict(todo))

            # 证据
            if agent_id is not None or score is not None or artifacts is not None or notes:
                ev = {"id": uid("ev"), "todo_id": todo.id, "agent_id": agent_id,
                      "score": score, "artifacts": artifacts or [], "notes": notes,
                      "timestamp": now()}
                ledger.upsert({"type": "evidence", "id": ev["id"]}, ev)

            self._maybe_advance_goal(todo.goal_id)
        return self._get_todo(todo.id)

    def refresh_state(self, goal_id: str,
                      agent_id: Optional[str] = None) -> StateSnapshot:
        goal = self._get_goal(goal_id)
        todos = self._list_todos(goal_id)
        by_status = {TodoStatus.READY: 0, TodoStatus.CLAIMED: 0, TodoStatus.DONE: 0,
                     TodoStatus.BLOCKED: 0, TodoStatus.FAILED: 0}
        claimed: List[Todo] = []
        for t in todos:
            by_status[t.status] = by_status.get(t.status, 0) + 1
            if t.status == TodoStatus.CLAIMED:
                claimed.append(t)
        next_todo = self._find_next_ready(goal_id)
        open_gates = [g for g in self._list_gates(goal_id) if g.status != GateStatus.PASSED]
        latest_cp = self._latest_checkpoint(goal_id)
        related = self._related_experiences(next_todo)
        return StateSnapshot(
            goal=goal, claimed_todos=claimed, next_todo=next_todo,
            progress={"done": by_status[TodoStatus.DONE], "total": len(todos),
                      "failed": by_status[TodoStatus.FAILED],
                      "blocked": by_status[TodoStatus.BLOCKED],
                      "ready": by_status[TodoStatus.READY],
                      "claimed": by_status[TodoStatus.CLAIMED]},
            open_gates=open_gates, latest_checkpoint=latest_cp,
            related_experiences=related,
        )

    def spend_slot(self, goal_id: str, n: int = 1) -> bool:
        with self._lock:
            goal = self._get_goal(goal_id)
            if goal is None:
                return False
            if goal.quota_total > 0 and goal.quota_used + n > goal.quota_total:
                return False
            goal.quota_used += n
            goal.updated_at = now()
            self._goal_ledger(goal_id).upsert({"type": "goal", "id": goal_id}, asdict(goal))
            return True

    # ---- 断点续跑 ----
    def checkpoint(self, goal_id: str, todo_id: Optional[str],
                   state: dict) -> Checkpoint:
        cp = Checkpoint(id=uid("cp"), goal_id=goal_id, todo_id=todo_id,
                        state=state, timestamp=now())
        row = asdict(cp)
        row["id"] = str(cp.id)
        self._goal_ledger(goal_id).upsert({"type": "checkpoint", "id": cp.id}, row)
        return cp

    def _latest_checkpoint(self, goal_id: str) -> Optional[Checkpoint]:
        rows = self._goal_ledger(goal_id).read_all("checkpoint")
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.get("timestamp", 0))
        return Checkpoint(**{k: v for k, v in latest.items() if k != "domain_state_key"})

    def restore_from_checkpoint(self, goal_id: str) -> Optional[dict]:
        cp = self._latest_checkpoint(goal_id)
        return cp.state if cp else None

    # ---- 经验沉淀 ----
    def add_experience(self, category: str, trigger: str, solution: str,
                       versions: Optional[str] = None) -> Experience:
        exp = Experience(id=uid("exp"), category=category, trigger=trigger,
                         solution=solution, versions=versions,
                         created_at=now())
        with self._lock:
            # 去重：相同 category+trigger 已存在则命中 +1
            for row in self._exp_ledger().read_all():
                if (row.get("category") == category and row.get("trigger") == trigger):
                    row["times_hit"] = int(row.get("times_hit", 1)) + 1
                    self._exp_ledger().upsert(row["domain_state_key"], row)
                    exp = Experience(**{k: v for k, v in row.items()
                                        if k != "domain_state_key"})
                    return exp
            self._exp_ledger().upsert({"type": "experience", "id": exp.id}, asdict(exp))
        return exp

    def hit_experience(self, exp_id: str) -> None:
        row = self._exp_ledger().read({"type": "experience", "id": exp_id})
        if row:
            row["times_hit"] = int(row.get("times_hit", 1)) + 1
            self._exp_ledger().upsert(row["domain_state_key"], row)

    def search_experience(self, category: Optional[str] = None,
                          keyword: Optional[str] = None) -> List[Experience]:
        out = []
        for row in self._exp_ledger().read_all("experience"):
            if category and row.get("category") != category:
                continue
            if keyword and keyword not in str(row.get("trigger", "")) \
                    and keyword not in str(row.get("solution", "")):
                continue
            out.append(Experience(**{k: v for k, v in row.items()
                                     if k != "domain_state_key"}))
        out.sort(key=lambda e: (-e.times_hit, -e.created_at))
        return out

    # ---- Gate ----
    def _list_gates(self, goal_id: str) -> List[Gate]:
        rows = self._goal_ledger(goal_id).read_all("gate")
        return [Gate(**{k: v for k, v in row.items() if k != "domain_state_key"})
                for row in rows]

    # ---- 内部逻辑（对齐 Kernel）----
    def _status_map(self, goal_id: str) -> Dict[str, str]:
        return {t.id: t.status for t in self._list_todos(goal_id)}

    def _find_next_ready(self, goal_id: str) -> Optional[Todo]:
        todos = self._list_todos(goal_id)
        status_by_id = {t.id: t.status for t in todos}
        for t in todos:
            if t.status != TodoStatus.READY:
                continue
            if dependencies_satisfied(t.dependencies, status_by_id):
                return t
        return None

    def _related_experiences(self, next_todo: Optional[Todo]) -> List[Experience]:
        if next_todo is None:
            return []
        return self.search_experience(category=next_todo.phase)

    def _maybe_advance_goal(self, goal_id: str) -> None:
        goal = self._get_goal(goal_id)
        if goal is None or is_terminal_goal(goal.status):
            return
        todos = self._list_todos(goal_id)
        if not todos:
            return
        if all(t.status == TodoStatus.DONE for t in todos):
            open_gates = [g for g in self._list_gates(goal_id)
                          if g.status != GateStatus.PASSED]
            if open_gates:
                self._set_goal_status(goal_id, GoalStatus.WAITING_GATE)
            else:
                self._set_goal_status(goal_id, GoalStatus.DONE)

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# LoopXBridge：真实 loopx CLI 的桥接点（升级路径）
# ---------------------------------------------------------------------------
class LoopXBridge:
    """封装真实 ``loopx`` CLI 调用。未安装时抛出清晰的引导错误。

    对应 LoopX 的真实命令（参考 dsh-loopx-plugin）：
      - ``loopx --registry <path> resolve-agent-thread --host-surface ...``
      - ``loopx quota should-run`` / ``loopx quota spend``
    """

    def __init__(self, registry: str, host_surface: str = "deepseek-harness-native"):
        self.registry = registry
        self.host_surface = host_surface

    def _run(self, *argv: str) -> str:
        import subprocess
        try:
            proc = subprocess.run(
                ["loopx", *argv], capture_output=True, text=True, timeout=120)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "未检测到 loopx CLI。请先安装：pip install 'loopx>=1.2.4'，"
                "或继续使用自研 SQLite 内核（默认）。") from exc
        if proc.returncode != 0:
            raise RuntimeError(f"loopx CLI 失败: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def resolve_agent_thread(self, thread_id: str) -> dict:
        out = self._run("--registry", self.registry, "--format", "json",
                        "resolve-agent-thread",
                        "--host-surface", self.host_surface,
                        "--thread-id", thread_id)
        return json.loads(out)

    def should_run(self, turn_instance_id: str) -> dict:
        out = self._run("quota", "should-run", "--turn-instance-id", turn_instance_id)
        return json.loads(out)


# ---------------------------------------------------------------------------
# 内核工厂：自研 SQLite / LoopX 可切换
# ---------------------------------------------------------------------------
def create_kernel(backend: str = "sqlite", **kwargs) -> Any:
    """创建状态内核。``backend`` 取值：

    - ``"sqlite"``（默认）：自研 SQLite 内核，``kwargs`` 传 ``db_path``。
    - ``"loopx"``：LoopX 风格 JSONL 内核，``kwargs`` 传 ``root``。
    """
    backend = backend.lower()
    if backend == "sqlite":
        from ..kernel import Kernel
        return Kernel(kwargs.get("db_path", ":memory:"))
    if backend in ("loopx", "loopx-jsonl"):
        return LoopXKernel(kwargs.get("root", "."))
    raise ValueError(f"未知内核 backend: {backend!r}（可选 sqlite / loopx）")


__all__ = [
    "LoopXKernel",
    "LoopXBridge",
    "create_kernel",
    "StateKernel",
]
