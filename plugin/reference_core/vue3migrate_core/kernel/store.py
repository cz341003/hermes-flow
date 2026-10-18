"""SQLite 持久化存储（durable state 的落盘层）。

设计要点：
- 单连接 + 线程锁（RLock），`check_same_thread=False`，WAL 模式。
- JSON 列表字段在此层完成序列化/反序列化。
- claim / spend_quota 用原子 UPDATE（WHERE 条件校验旧值）保证并发安全。
- 零第三方依赖，仅用标准库 sqlite3 / json / uuid / time / threading。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

from .models import (
    Checkpoint,
    Evidence,
    Experience,
    Gate,
    Goal,
    Todo,
)
from .schema import SCHEMA_SQL


def now() -> float:
    return time.time()


def uid(prefix: str = "") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _loads(text: Optional[str], default):
    if text is None:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


class SQLiteStore:
    def __init__(self, db_path: str):
        self._path = str(db_path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                # 优雅关闭：checkpoint 并切回 DELETE 日志，释放 WAL 文件句柄
                # （Windows 上 WAL 句柄延迟释放会导致文件占用，见 M7 适配器单测）
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.execute("PRAGMA journal_mode = DELETE")
                self._conn.commit()
            except sqlite3.Error:
                pass  # 连接可能已关闭或为内存库
            self._conn.close()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params=()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------------
    # Goal
    # ------------------------------------------------------------------
    def create_goal(self, title: str, description: str = "",
                    scope: Optional[List[str]] = None,
                    workflow_id: str = "",
                    quota_total: int = 0,
                    goal_id: Optional[str] = None) -> Goal:
        gid = goal_id or uid("goal")
        ts = now()
        goal = Goal(
            id=gid, title=title, description=description,
            scope=list(scope or []), workflow_id=workflow_id,
            quota_total=quota_total, quota_used=0,
            created_at=ts, updated_at=ts,
        )
        self._execute(
            "INSERT INTO goal (id, title, description, scope, status, workflow_id,"
            " quota_total, quota_used, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (goal.id, goal.title, goal.description, _dumps(goal.scope),
             goal.status, goal.workflow_id, goal.quota_total, goal.quota_used,
             goal.created_at, goal.updated_at),
        )
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        rows = self._query("SELECT * FROM goal WHERE id = ?", (goal_id,))
        return self._row_to_goal(rows[0]) if rows else None

    def list_goals(self) -> List[Goal]:
        rows = self._query("SELECT * FROM goal ORDER BY created_at")
        return [self._row_to_goal(r) for r in rows]

    def set_goal_status(self, goal_id: str, status: str) -> Goal:
        self._execute(
            "UPDATE goal SET status = ?, updated_at = ? WHERE id = ?",
            (status, now(), goal_id),
        )
        return self.get_goal(goal_id)  # type: ignore[return-value]

    def set_goal_field(self, goal_id: str, **fields) -> Goal:
        allowed = {"description", "workflow_id", "quota_total"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise KeyError(f"非法 goal 字段: {k}")
            sets.append(f"{k} = ?")
            params.append(v)
        sets.append("updated_at = ?")
        params.append(now())
        params.append(goal_id)
        self._execute(f"UPDATE goal SET {', '.join(sets)} WHERE id = ?", params)
        return self.get_goal(goal_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Todo
    # ------------------------------------------------------------------
    def create_todo(self, goal_id: str, file_path: str, phase: str,
                    dependencies: Optional[List[str]] = None,
                    max_attempts: int = 3,
                    todo_id: Optional[str] = None) -> Todo:
        tid = todo_id or uid("todo")
        ts = now()
        todo = Todo(
            id=tid, goal_id=goal_id, file_path=file_path, phase=phase,
            dependencies=list(dependencies or []), max_attempts=max_attempts,
            created_at=ts, updated_at=ts,
        )
        self._execute(
            "INSERT INTO todo (id, goal_id, file_path, phase, dependencies, status,"
            " attempts, max_attempts, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (todo.id, todo.goal_id, todo.file_path, todo.phase,
             _dumps(todo.dependencies), todo.status, todo.attempts,
             todo.max_attempts, todo.created_at, todo.updated_at),
        )
        return todo

    def get_todo(self, todo_id: str) -> Optional[Todo]:
        rows = self._query("SELECT * FROM todo WHERE id = ?", (todo_id,))
        return self._row_to_todo(rows[0]) if rows else None

    def list_todos(self, goal_id: str) -> List[Todo]:
        rows = self._query(
            "SELECT * FROM todo WHERE goal_id = ? ORDER BY created_at, id", (goal_id,))
        return [self._row_to_todo(r) for r in rows]

    def _update_todo_impl(self, todo_id: str, **fields) -> Todo:
        allowed = {
            "file_path", "phase", "owner_agent", "status", "attempts",
            "max_attempts", "score", "error", "lease_expires_at",
        }
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise KeyError(f"非法 todo 字段: {k}")
            sets.append(f"{k} = ?")
            params.append(v)
        sets.append("updated_at = ?")
        params.append(now())
        params.append(todo_id)
        self._execute(f"UPDATE todo SET {', '.join(sets)} WHERE id = ?", params)
        return self.get_todo(todo_id)  # type: ignore[return-value]

    def update_todo(self, todo_id: str, **fields) -> Todo:
        return self._update_todo_impl(todo_id, **fields)

    def claim_todo(self, todo_id: str, agent_id: str,
                   lease_seconds: float = 300.0) -> bool:
        """原子认领：仅当当前 status == 'ready' 时成功（防并发冲突）。"""
        ts = now()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE todo SET status = 'claimed', owner_agent = ?,"
                " lease_expires_at = ?, updated_at = ?"
                " WHERE id = ? AND status = 'ready'",
                (agent_id, ts + lease_seconds, ts, todo_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def reset_todo_status(self, todo_id: str, status: str,
                          owner_agent: Optional[str] = None) -> Todo:
        fields = {"status": status, "owner_agent": owner_agent,
                  "lease_expires_at": None}
        return self._update_todo_impl(todo_id, **fields)

    # ------------------------------------------------------------------
    # Quota
    # ------------------------------------------------------------------
    def spend_quota(self, goal_id: str, n: int = 1) -> bool:
        """原子消耗槽位：仅在 quota 未超限时成功。quota_total==0 视为不限。"""
        goal = self.get_goal(goal_id)
        if goal is None:
            return False
        if goal.quota_total <= 0:
            self._execute(
                "UPDATE goal SET quota_used = quota_used + ?, updated_at = ?"
                " WHERE id = ?", (n, now(), goal_id))
            return True
        with self._lock:
            cur = self._conn.execute(
                "UPDATE goal SET quota_used = quota_used + ?, updated_at = ?"
                " WHERE id = ? AND quota_used + ? <= quota_total",
                (n, now(), goal_id, n),
            )
            self._conn.commit()
            return cur.rowcount == 1

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------
    def create_gate(self, goal_id: str, kind: str, question: str = "",
                    threshold: Optional[float] = None,
                    gate_id: Optional[str] = None) -> Gate:
        gid = gate_id or uid("gate")
        gate = Gate(id=gid, goal_id=goal_id, kind=kind, question=question,
                    threshold=threshold)
        self._execute(
            "INSERT INTO gate (id, goal_id, kind, question, threshold, status)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (gate.id, gate.goal_id, gate.kind, gate.question, gate.threshold,
             gate.status),
        )
        return gate

    def list_gates(self, goal_id: str) -> List[Gate]:
        rows = self._query("SELECT * FROM gate WHERE goal_id = ?", (goal_id,))
        return [self._row_to_gate(r) for r in rows]

    def set_gate_status(self, gate_id: str, status: str) -> Gate:
        self._execute("UPDATE gate SET status = ? WHERE id = ?", (status, gate_id))
        rows = self._query("SELECT * FROM gate WHERE id = ?", (gate_id,))
        return self._row_to_gate(rows[0])

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------
    def add_evidence(self, todo_id: str, agent_id: Optional[str],
                     score: Optional[float], artifacts: Optional[List[str]],
                     notes: str = "") -> Evidence:
        ev = Evidence(
            id=uid("ev"), todo_id=todo_id, agent_id=agent_id, score=score,
            artifacts=list(artifacts or []), notes=notes, timestamp=now(),
        )
        self._execute(
            "INSERT INTO evidence (id, todo_id, agent_id, score, artifacts, notes, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ev.id, ev.todo_id, ev.agent_id, ev.score, _dumps(ev.artifacts),
             ev.notes, ev.timestamp),
        )
        return ev

    def list_evidence(self, todo_id: str) -> List[Evidence]:
        rows = self._query(
            "SELECT * FROM evidence WHERE todo_id = ? ORDER BY timestamp", (todo_id,))
        return [self._row_to_evidence(r) for r in rows]

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------
    def save_checkpoint(self, goal_id: str, todo_id: Optional[str],
                        state: dict) -> Checkpoint:
        cp = Checkpoint(goal_id=goal_id, todo_id=todo_id, state=state, timestamp=now())
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO checkpoint (goal_id, todo_id, state, timestamp)"
                " VALUES (?, ?, ?, ?)",
                (goal_id, todo_id, _dumps(state), cp.timestamp),
            )
            self._conn.commit()
            cp.id = cur.lastrowid
        return cp

    def latest_checkpoint(self, goal_id: str) -> Optional[Checkpoint]:
        rows = self._query(
            "SELECT * FROM checkpoint WHERE goal_id = ? ORDER BY id DESC LIMIT 1",
            (goal_id,))
        return self._row_to_checkpoint(rows[0]) if rows else None

    def list_checkpoints(self, goal_id: str) -> List[Checkpoint]:
        rows = self._query(
            "SELECT * FROM checkpoint WHERE goal_id = ? ORDER BY id", (goal_id,))
        return [self._row_to_checkpoint(r) for r in rows]

    # ------------------------------------------------------------------
    # Experience
    # ------------------------------------------------------------------
    def add_experience(self, category: str, trigger: str, solution: str,
                       versions: Optional[str] = None,
                       exp_id: Optional[str] = None) -> Experience:
        eid = exp_id or uid("exp")
        exp = Experience(id=eid, category=category, trigger=trigger,
                         solution=solution, versions=versions, created_at=now())
        self._execute(
            "INSERT INTO experience (id, category, trigger, solution, versions, times_hit, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (exp.id, exp.category, exp.trigger, exp.solution, exp.versions,
             exp.times_hit, exp.created_at),
        )
        return exp

    def hit_experience(self, exp_id: str) -> None:
        self._execute(
            "UPDATE experience SET times_hit = times_hit + 1 WHERE id = ?", (exp_id,))

    def search_experience(self, category: Optional[str] = None,
                          keyword: Optional[str] = None) -> List[Experience]:
        sql = "SELECT * FROM experience"
        conds, params = [], []
        if category:
            conds.append("category = ?")
            params.append(category)
        if keyword:
            conds.append("(trigger LIKE ? OR solution LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY times_hit DESC, created_at DESC"
        rows = self._query(sql, params)
        return [self._row_to_experience(r) for r in rows]

    # ------------------------------------------------------------------
    # row -> dataclass 映射
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_goal(r: sqlite3.Row) -> Goal:
        return Goal(
            id=r["id"], title=r["title"], description=r["description"],
            scope=_loads(r["scope"], []), status=r["status"],
            workflow_id=r["workflow_id"], quota_total=r["quota_total"],
            quota_used=r["quota_used"], created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    @staticmethod
    def _row_to_todo(r: sqlite3.Row) -> Todo:
        return Todo(
            id=r["id"], goal_id=r["goal_id"], file_path=r["file_path"],
            phase=r["phase"], dependencies=_loads(r["dependencies"], []),
            owner_agent=r["owner_agent"], status=r["status"],
            attempts=r["attempts"], max_attempts=r["max_attempts"],
            score=r["score"], error=r["error"],
            lease_expires_at=r["lease_expires_at"],
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    @staticmethod
    def _row_to_gate(r: sqlite3.Row) -> Gate:
        return Gate(
            id=r["id"], goal_id=r["goal_id"], kind=r["kind"],
            question=r["question"], threshold=r["threshold"], status=r["status"],
        )

    @staticmethod
    def _row_to_evidence(r: sqlite3.Row) -> Evidence:
        return Evidence(
            id=r["id"], todo_id=r["todo_id"], agent_id=r["agent_id"],
            score=r["score"], artifacts=_loads(r["artifacts"], []),
            notes=r["notes"], timestamp=r["timestamp"],
        )

    @staticmethod
    def _row_to_checkpoint(r: sqlite3.Row) -> Checkpoint:
        return Checkpoint(
            id=r["id"], goal_id=r["goal_id"], todo_id=r["todo_id"],
            state=_loads(r["state"], {}), timestamp=r["timestamp"],
        )

    @staticmethod
    def _row_to_experience(r: sqlite3.Row) -> Experience:
        return Experience(
            id=r["id"], category=r["category"], trigger=r["trigger"],
            solution=r["solution"], versions=r["versions"],
            times_hit=r["times_hit"], created_at=r["created_at"],
        )
