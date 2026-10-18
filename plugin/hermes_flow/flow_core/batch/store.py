"""批次持久化（SQLite WAL）：批次 / 文件 / 回执 / 租约。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import BatchItemRecord, BatchPlan, BatchPolicy, BatchRecord

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS batch_groups(
  id TEXT PRIMARY KEY, run_id TEXT, node_id TEXT, expert_id TEXT,
  total_files INTEGER, total_batches INTEGER, done_batches INTEGER DEFAULT 0,
  aggregate_score REAL, aggregate_verdict TEXT, status TEXT,
  policy_json TEXT, created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS batches(
  id TEXT PRIMARY KEY, group_id TEXT, wave INTEGER, seq INTEGER, status TEXT,
  attempt INTEGER DEFAULT 0, split_depth INTEGER DEFAULT 0,
  files_json TEXT, workspace_baseline_json TEXT,
  score REAL, verdict TEXT, lease_owner TEXT, lease_expires_at INTEGER,
  version INTEGER DEFAULT 0, agent_correlation_id TEXT,
  started_at INTEGER, ended_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_batches_group ON batches(group_id, status);
CREATE TABLE IF NOT EXISTS batch_items(
  id TEXT PRIMARY KEY, group_id TEXT, batch_id TEXT, file_path TEXT,
  status TEXT, attempt_id TEXT, base_hash TEXT, staged_path TEXT,
  applied_hash TEXT, attempts INTEGER DEFAULT 0,
  evidence_json TEXT, updated_at INTEGER,
  UNIQUE(group_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_items_batch ON batch_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_items_group ON batch_items(group_id, status);
CREATE TABLE IF NOT EXISTS batch_receipts(
  id TEXT PRIMARY KEY, batch_id TEXT, attempt INTEGER, event TEXT,
  payload_json TEXT, created_at INTEGER,
  UNIQUE(batch_id, attempt, event)
);
"""

_TERMINAL = ("done", "skipped", "failed", "split")


def _now() -> int:
    return int(time.time())


class BatchStore:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------- helpers
    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _commit(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    def receipt(self, batch_id: str, attempt: int, event: str, payload: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO batch_receipts(id,batch_id,attempt,event,payload_json,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (uuid.uuid4().hex, batch_id, attempt, event,
                 json.dumps(payload, ensure_ascii=False), _now()))

    # -------------------------------------------------------------- groups
    def create_group(self, *, group_id: str, run_id: str, node_id: str, expert_id: str,
                     plan: BatchPlan, policy: BatchPolicy) -> None:
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO batch_groups(id,run_id,node_id,expert_id,total_files,total_batches,"
                "done_batches,status,policy_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (group_id, run_id, node_id, expert_id, plan.total_files,
                 plan.total_batches, 0, "running",
                 json.dumps(policy.to_dict(), ensure_ascii=False), now, now))
            item_id = 0
            for batch in plan.batches:
                # 批次 id 必须跨 group 唯一：用 group 前缀命名空间
                bid = f"{group_id}--b{batch.seq:04d}"
                files = [f.to_dict() for f in batch.files]
                self._conn.execute(
                    "INSERT INTO batches(id,group_id,wave,seq,status,attempt,split_depth,"
                    "files_json,lease_owner,lease_expires_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (bid, group_id, batch.wave, batch.seq, "planned", 0, 0,
                     json.dumps(files, ensure_ascii=False), "", 0, 0))
                for f in batch.files:
                    item_id += 1
                    self._conn.execute(
                        "INSERT INTO batch_items(id,group_id,batch_id,file_path,status,attempt_id,"
                        "base_hash,staged_path,applied_hash,attempts,evidence_json,updated_at)"
                        " VALUES(?,?,?,?,?,?,?,?,?,0,'{}',?)",
                        (f"i-{item_id:06d}-{uuid.uuid4().hex[:6]}", group_id, bid, f.path, "pending",
                         "", f.sha256, "", "", now))
            self._conn.execute(
                "UPDATE batch_groups SET updated_at=? WHERE id=?", (now, group_id))
            self._promote_ready(group_id)

    def _promote_ready(self, group_id: str) -> None:
        """把最早未完成 wave 的 planned 批次置为 ready（同 wave 可多个）。"""
        rows = self._execute(
            "SELECT id,wave,status FROM batches WHERE group_id=? ORDER BY wave,seq",
            (group_id,)).fetchall()
        open_waves = [r["wave"] for r in rows if r["status"] not in _TERMINAL]
        if not open_waves:
            return
        first = min(open_waves)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE batches SET status='ready' WHERE group_id=? AND wave=? AND status='planned'",
                (group_id, first))

    # -------------------------------------------------------------- batches
    def get_batch(self, batch_id: str) -> Optional[BatchRecord]:
        row = self._execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        return self._row_to_batch(row) if row else None

    def list_batches(self, group_id: str) -> List[BatchRecord]:
        rows = self._execute(
            "SELECT * FROM batches WHERE group_id=? ORDER BY wave,seq", (group_id,)).fetchall()
        return [self._row_to_batch(r) for r in rows]

    def _row_to_batch(self, row: sqlite3.Row) -> BatchRecord:
        return BatchRecord(
            id=row["id"], group_id=row["group_id"], wave=row["wave"], seq=row["seq"],
            status=row["status"], attempt=row["attempt"], split_depth=row["split_depth"],
            files=json.loads(row["files_json"] or "[]"), score=row["score"],
            verdict=row["verdict"] or "", lease_owner=row["lease_owner"] or "",
            lease_expires_at=row["lease_expires_at"] or 0,
            agent_correlation_id=row["agent_correlation_id"] or "",
        )

    def get_group_policy(self, group_id: str) -> Dict[str, Any]:
        row = self._execute("SELECT policy_json FROM batch_groups WHERE id=?", (group_id,)).fetchone()
        if not row or not row["policy_json"]:
            return {}
        try:
            return dict(json.loads(row["policy_json"]))
        except Exception:  # noqa: BLE001
            return {}

    def claim_next(self, group_id: str, owner: str, ttl_seconds: int = 600,
                   max_concurrent: int = 1) -> Optional[BatchRecord]:
        """原子认领：只允许最早未完成 wave 的 ready 批；可抢占租约过期的 running 批。

        ``max_concurrent`` >1 时允许同 wave 多批并行（batch 级串行约束放宽）。
        """
        now = _now()
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT * FROM batches WHERE group_id=? ORDER BY wave,seq", (group_id,)).fetchall()
            active = [r for r in rows if r["status"] == "running"
                      and (r["lease_expires_at"] or 0) >= now]
            if len(active) >= max(1, int(max_concurrent)):
                return None
            open_waves = [r["wave"] for r in rows if r["status"] not in _TERMINAL]
            if not open_waves:
                return None
            first = min(open_waves)
            candidates = [r for r in rows if r["wave"] == first
                          and (r["status"] == "ready"
                               or (r["status"] == "running"
                                   and (r["lease_expires_at"] or 0) < now))]
            if not candidates:
                return None
            row = candidates[0]
            cur = self._conn.execute(
                "UPDATE batches SET status='running', lease_owner=?, lease_expires_at=?,"
                " attempt=attempt+1, started_at=?, version=version+1"
                " WHERE id=? AND status IN ('ready','running') AND version=?",
                (owner, now + ttl_seconds, now, row["id"], row["version"]))
            if cur.rowcount != 1:
                return None
            self._conn.execute("UPDATE batch_groups SET updated_at=? WHERE id=?", (now, group_id))
            updated = self._conn.execute("SELECT * FROM batches WHERE id=?", (row["id"],)).fetchone()
        batch = self._row_to_batch(updated)
        self.receipt(batch.id, batch.attempt, "claimed", {"owner": owner, "ttl": ttl_seconds})
        return batch

    def heartbeat(self, batch_id: str, owner: str, ttl_seconds: int = 600) -> bool:
        cur = self._commit(
            "UPDATE batches SET lease_expires_at=? WHERE id=? AND lease_owner=? AND status='running'",
            (_now() + ttl_seconds, batch_id, owner))
        return cur.rowcount == 1

    def complete(self, batch_id: str, *, score: Optional[float] = None,
                 verdict: str = "pass") -> None:
        batch = self.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE batches SET status='done', score=?, verdict=?, ended_at=?,"
                " lease_owner='', lease_expires_at=0, version=version+1 WHERE id=?",
                (score, verdict, _now(), batch_id))
            self._conn.execute(
                "UPDATE batch_groups SET done_batches=done_batches+1, updated_at=? WHERE id=?",
                (_now(), batch.group_id))
            self._conn.execute(
                "UPDATE batch_items SET status='applied', updated_at=? WHERE batch_id=? AND status='staged'",
                (_now(), batch_id))
        self.receipt(batch_id, batch.attempt, "completed", {"score": score, "verdict": verdict})
        self._promote_ready(batch.group_id)

    def fail(self, batch_id: str, reason: str = "", *, max_attempts: int = 3) -> str:
        batch = self.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        status = "ready" if batch.attempt < max_attempts else "failed"
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE batches SET status=?, verdict=?, lease_owner='', lease_expires_at=0,"
                " version=version+1 WHERE id=?",
                (status, str(reason)[:200], batch_id))
        self.receipt(batch_id, batch.attempt, "failed", {"reason": reason, "next": status})
        if status == "failed":
            self._promote_ready(batch.group_id)
        return status

    def requeue(self, batch_id: str, reason: str = "") -> bool:
        """不消耗 attempt 地把 running 批退回 ready（429/无可用父会话/可重试错误）。"""
        batch = self.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        cur = self._commit(
            "UPDATE batches SET status='ready', verdict=?, lease_owner='', lease_expires_at=0,"
            " attempt=CASE WHEN attempt>0 THEN attempt-1 ELSE 0 END, version=version+1"
            " WHERE id=? AND status='running'",
            (str(reason)[:200], batch_id))
        if cur.rowcount == 1:
            self.receipt(batch_id, batch.attempt, "requeued", {"reason": reason})
        return cur.rowcount == 1

    def retry_failed(self, group_id: str, reason: str = "manual rerun") -> int:
        """把 failed 批重置为 ready（节点级重跑）。"""
        rows = self._execute(
            "SELECT id, attempt FROM batches WHERE group_id=? AND status='failed'",
            (group_id,)).fetchall()
        if not rows:
            return 0
        now = _now()
        with self._lock, self._conn:
            for row in rows:
                self._conn.execute(
                    "UPDATE batches SET status='ready', attempt=0, verdict=?, lease_owner='',"
                    " lease_expires_at=0, version=version+1 WHERE id=?",
                    (reason[:200], row["id"]))
                self.receipt(row["id"], row["attempt"], "manual_retried", {"reason": reason})
            self._conn.execute("UPDATE batch_groups SET updated_at=? WHERE id=?", (now, group_id))
            self._promote_ready(group_id)
        return len(rows)

    def split(self, batch_id: str, *, new_ids: Optional[List[str]] = None) -> List[str]:
        """把一个批次按文件二分（最多 max_split_depth 层），返回新批次 id。"""
        batch = self.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        files = batch.files
        if len(files) <= 1:
            return []
        mid = len(files) // 2
        chunks = [files[:mid], files[mid:]]
        ids = new_ids or [f"{batch.id}-s{i+1}" for i in range(len(chunks))]
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE batches SET status='split', lease_owner='', lease_expires_at=0,"
                " version=version+1, ended_at=? WHERE id=?", (now, batch_id))
            n = self._next_item_seq(batch.group_id)
            for bid, chunk in zip(ids, chunks):
                self._conn.execute(
                    "INSERT INTO batches(id,group_id,wave,seq,status,attempt,split_depth,"
                    "files_json,lease_owner,lease_expires_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (bid, batch.group_id, batch.wave, batch.seq, "ready", 0,
                     batch.split_depth + 1, json.dumps(chunk, ensure_ascii=False), "", 0, 0))
                paths = [f["path"] for f in chunk]
                marks = ",".join("?" for _ in paths)
                self._conn.execute(
                    f"UPDATE batch_items SET batch_id=?, status='pending', attempt_id='',"
                    f" staged_path='', applied_hash='', updated_at=?"
                    f" WHERE group_id=? AND file_path IN ({marks})",
                    (bid, now, batch.group_id, *paths))
        self.receipt(batch_id, batch.attempt, "split", {"new_ids": ids})
        self._promote_ready(batch.group_id)
        return ids

    def repair(self, batch_id: str, failed_paths: List[str], *, new_id: Optional[str] = None) -> Optional[str]:
        """把失败文件组成 repair 子批（同 wave，优先执行）；限制 repair 轮数。"""
        batch = self.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        if batch.id.count("-r") >= 3:
            return None
        wanted = set(failed_paths)
        files = [f for f in batch.files if f.get("path") in wanted]
        if not files:
            return None
        rid = new_id or f"{batch.id}-r{batch.attempt}"
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO batches(id,group_id,wave,seq,status,attempt,split_depth,"
                "files_json,lease_owner,lease_expires_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rid, batch.group_id, batch.wave, batch.seq, "ready", 0,
                 batch.split_depth, json.dumps(files, ensure_ascii=False), "", 0, 0))
            n = self._next_item_seq(batch.group_id)
            paths = [f["path"] for f in files]
            marks = ",".join("?" for _ in paths)
            self._conn.execute(
                f"UPDATE batch_items SET batch_id=?, status='pending', attempt_id='',"
                f" staged_path='', applied_hash='', updated_at=?"
                f" WHERE group_id=? AND file_path IN ({marks})",
                (rid, now, batch.group_id, *paths))
        self.receipt(batch_id, batch.attempt, "repair", {"new_id": rid, "files": failed_paths})
        return rid

    def _next_item_seq(self, group_id: str) -> int:
        row = self._execute("SELECT COUNT(*) AS n FROM batch_items WHERE group_id=?", (group_id,)).fetchone()
        return int(row["n"]) if row else 0

    # ---------------------------------------------------------------- items
    def list_items(self, batch_id: str) -> List[BatchItemRecord]:
        rows = self._execute(
            "SELECT * FROM batch_items WHERE batch_id=? ORDER BY file_path", (batch_id,)).fetchall()
        return [BatchItemRecord(
            id=r["id"], group_id=r["group_id"], batch_id=r["batch_id"], file_path=r["file_path"],
            status=r["status"], attempt_id=r["attempt_id"] or "", base_hash=r["base_hash"] or "",
            staged_path=r["staged_path"] or "", applied_hash=r["applied_hash"] or "",
            attempts=r["attempts"] or 0,
            evidence=json.loads(r["evidence_json"] or "{}"),
        ) for r in rows]

    def set_item(self, group_id: str, file_path: str, *, status: str,
                 attempt_id: str = "", staged_path: str = "", applied_hash: str = "",
                 evidence: Optional[Dict[str, Any]] = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE batch_items SET status=?, attempt_id=?, staged_path=?, applied_hash=?,"
                " attempts=attempts+1, evidence_json=?, updated_at=? WHERE group_id=? AND file_path=?",
                (status, attempt_id, staged_path, applied_hash,
                 json.dumps(evidence or {}, ensure_ascii=False), _now(), group_id, file_path))

    def set_baseline(self, batch_id: str, baseline: Dict[str, Any]) -> None:
        self._commit("UPDATE batches SET workspace_baseline_json=? WHERE id=?",
                     (json.dumps(baseline, ensure_ascii=False), batch_id))

    def get_baseline(self, batch_id: str) -> Dict[str, Any]:
        row = self._execute("SELECT workspace_baseline_json FROM batches WHERE id=?", (batch_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else {}

    # --------------------------------------------------------------- status
    def group_status(self, group_id: str) -> Dict[str, Any]:
        rows = self.list_batches(group_id)
        items = self._execute(
            "SELECT status, COUNT(*) AS n FROM batch_items WHERE group_id=? GROUP BY status",
            (group_id,)).fetchall()
        item_counts = {r["status"]: r["n"] for r in items}
        done = sum(1 for b in rows if b.status in ("done", "skipped", "split"))
        return {
            "group_id": group_id,
            "total_batches": len(rows),
            "done_batches": done,
            "batches": [b.to_dict() for b in rows],
            "items": item_counts,
            "running": [b.id for b in rows if b.status == "running"],
            "ready": [b.id for b in rows if b.status == "ready"],
            "failed": [b.id for b in rows if b.status == "failed"],
            "split": [b.id for b in rows if b.status == "split"],
        }

    def next_ready(self, group_id: str) -> Optional[BatchRecord]:
        rows = self.list_batches(group_id)
        open_waves = [b.wave for b in rows if b.status not in _TERMINAL]
        if not open_waves:
            return None
        first = min(open_waves)
        for b in rows:
            if b.wave == first and b.status == "ready":
                return b
        return None
