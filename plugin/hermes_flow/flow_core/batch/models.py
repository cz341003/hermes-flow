"""批次数据模型（FR-10）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BATCH_STATUSES = ("planned", "ready", "running", "gated", "done", "failed", "split", "skipped")
ITEM_STATUSES = ("pending", "running", "staged", "applied", "done", "failed", "manual")


@dataclass
class FileItem:
    path: str
    size: int = 0
    deps: List[str] = field(default_factory=list)
    risk: str = "low"
    priority: int = 0
    sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path, "size": self.size, "deps": list(self.deps),
            "risk": self.risk, "priority": self.priority, "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileItem":
        return cls(
            path=str(data["path"]),
            size=int(data.get("size", 0)),
            deps=[str(d) for d in data.get("deps", [])],
            risk=str(data.get("risk", "low")),
            priority=int(data.get("priority", 0)),
            sha256=str(data.get("sha256", "")),
        )


@dataclass
class BatchPolicy:
    max_files_per_batch: int = 7
    context_budget_chars: int = 28000
    max_concurrent_batches: int = 1
    max_batches_per_tick: int = 10
    tick_budget_seconds: int = 600
    wait_slice_seconds: int = 60
    batch_timeout_seconds: int = 1800
    max_attempts: int = 3
    max_split_depth: int = 2
    inner_loop: str = "serial"
    split_on_failure: bool = True
    quality_gate_per_batch: bool = True
    write_mode: str = "staging_apply"
    max_batch_size_cap: int = 12

    @classmethod
    def from_loop_policy(cls, policy: Optional[Dict[str, Any]]) -> "BatchPolicy":
        p = dict(policy or {})
        return cls(
            max_files_per_batch=max(1, int(p.get("max_files_per_batch", 7))),
            context_budget_chars=max(4000, int(p.get("context_budget_chars", 28000))),
            max_concurrent_batches=max(1, int(p.get("max_concurrent_batches", 1))),
            max_batches_per_tick=max(1, int(p.get("max_batches_per_tick", 10))),
            tick_budget_seconds=max(1, int(p.get("tick_budget_seconds", 600))),
            wait_slice_seconds=max(5, int(p.get("wait_slice_seconds", 60))),
            batch_timeout_seconds=max(60, int(p.get("batch_timeout_seconds", 1800))),
            max_attempts=max(1, int(p.get("max_attempts", 3))),
            max_split_depth=max(0, int(p.get("max_split_depth", 2))),
            inner_loop=str(p.get("inner_loop", "serial")),
            split_on_failure=bool(p.get("split_on_failure", True)),
            quality_gate_per_batch=bool(p.get("quality_gate_per_batch", True)),
            write_mode=str(p.get("write_mode", "staging_apply")),
            max_batch_size_cap=max(1, int(p.get("max_batch_size_cap", 12))),
        )

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class PlannedBatch:
    id: str
    wave: int
    seq: int
    files: List[FileItem] = field(default_factory=list)
    priority: str = "normal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "wave": self.wave, "seq": self.seq,
            "files": [f.to_dict() for f in self.files], "priority": self.priority,
        }


@dataclass
class BatchPlan:
    batches: List[PlannedBatch] = field(default_factory=list)
    total_files: int = 0

    @property
    def total_batches(self) -> int:
        return len(self.batches)

    @property
    def waves(self) -> int:
        return max((b.wave for b in self.batches), default=-1) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_batches": self.total_batches,
            "waves": self.waves,
            "batches": [b.to_dict() for b in self.batches],
        }


@dataclass
class BatchRecord:
    id: str
    group_id: str
    wave: int
    seq: int
    status: str
    attempt: int
    split_depth: int
    files: List[Dict[str, Any]] = field(default_factory=list)
    score: Optional[float] = None
    verdict: str = ""
    lease_owner: str = ""
    lease_expires_at: int = 0
    agent_correlation_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "group_id": self.group_id, "wave": self.wave,
            "seq": self.seq, "status": self.status, "attempt": self.attempt,
            "split_depth": self.split_depth, "files": self.files,
            "score": self.score, "verdict": self.verdict,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
            "agent_correlation_id": self.agent_correlation_id,
        }


@dataclass
class BatchItemRecord:
    id: str
    group_id: str
    batch_id: str
    file_path: str
    status: str
    attempt_id: str = ""
    base_hash: str = ""
    staged_path: str = ""
    applied_hash: str = ""
    attempts: int = 0
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)
