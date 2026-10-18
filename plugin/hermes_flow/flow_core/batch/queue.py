"""BatchQueue：批次生命周期门面（规划→认领→回灌→应用→完成/失败/拆分/修复）。"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import BatchPlan, BatchPolicy, BatchRecord
from .store import BatchStore


class BatchQueue:
    def __init__(self, store: BatchStore, policy: Optional[BatchPolicy] = None):
        self.store = store
        self.policy = policy or BatchPolicy()

    def _policy(self, group_id: str) -> BatchPolicy:
        """优先使用 group 创建时持久化的策略（节点/专家配置），否则用队列默认。"""
        stored = self.store.get_group_policy(group_id)
        return BatchPolicy.from_loop_policy(stored) if stored else self.policy

    def create_group(self, *, plan: BatchPlan, run_id: str, node_id: str, expert_id: str,
                     group_id: Optional[str] = None, policy: Optional[BatchPolicy] = None) -> str:
        gid = group_id or f"g-{run_id}-{node_id}"
        self.store.create_group(group_id=gid, run_id=run_id, node_id=node_id,
                                expert_id=expert_id, plan=plan, policy=policy or self.policy)
        return gid

    def policy_for(self, group_id: str) -> BatchPolicy:
        return self._policy(group_id)

    def claim_next(self, group_id: str, owner: str,
                   max_concurrent: Optional[int] = None) -> Optional[BatchRecord]:
        policy = self._policy(group_id)
        return self.store.claim_next(
            group_id, owner, ttl_seconds=policy.tick_budget_seconds,
            max_concurrent=max_concurrent or policy.max_concurrent_batches)

    def heartbeat(self, batch_id: str, owner: str) -> bool:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            return False
        return self.store.heartbeat(batch_id, owner,
                                    ttl_seconds=self._policy(batch.group_id).tick_budget_seconds)

    def complete(self, batch_id: str, *, score: Optional[float] = None, verdict: str = "pass") -> None:
        self.store.complete(batch_id, score=score, verdict=verdict)

    def fail(self, batch_id: str, reason: str = "") -> str:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        return self.store.fail(batch_id, reason,
                               max_attempts=self._policy(batch.group_id).max_attempts)

    def requeue(self, batch_id: str, reason: str = "") -> bool:
        return self.store.requeue(batch_id, reason)

    def retry_failed(self, group_id: str, reason: str = "manual rerun") -> int:
        return self.store.retry_failed(group_id, reason)

    def split(self, batch_id: str) -> List[str]:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        if batch.split_depth >= self._policy(batch.group_id).max_split_depth:
            return []
        return self.store.split(batch_id)

    def repair(self, batch_id: str, failed_paths: List[str]) -> Optional[str]:
        return self.store.repair(batch_id, failed_paths)

    def status(self, group_id: str) -> Dict[str, Any]:
        return self.store.group_status(group_id)

    # ------------------------------------------------------------- ingest
    def ingest(self, batch_id: str, results: List[Dict[str, Any]], *,
               attempt_id: str = "", staging_root: Optional[str] = None,
               project_root: Optional[str] = None) -> Dict[str, Any]:
        """回灌子代理逐文件结果：写 batch_items（staged/failed/manual）。"""
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        expected = {f["path"] for f in batch.files}
        seen: set[str] = set()
        failed: List[str] = []
        missing: List[str] = []
        for item in results:
            path = str(item.get("path", ""))
            if path not in expected:
                continue
            seen.add(path)
            status = str(item.get("status", "done"))
            if status == "failed":
                failed.append(path)
                mapped = "failed"
            elif status == "manual":
                mapped = "manual"
            else:
                mapped = "staged"
            staged = str(item.get("staged_path") or "")
            if not staged and staging_root and project_root:
                staged = str(Path(staging_root) / path)
            self.store.set_item(batch.group_id, path, status=mapped, attempt_id=attempt_id,
                                staged_path=staged, evidence=item)
        missing = sorted(expected - seen)
        return {"batch_id": batch_id, "failed": failed, "missing": missing,
                "ingested": len(seen)}

    # -------------------------------------------------------------- apply
    def apply(self, batch_id: str, *, project_root: str, staging_root: str,
              backup_root: str) -> Dict[str, Any]:
        """校验 staging 集合并原子应用到工作区；返回逐文件结果。"""
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        project = Path(project_root).resolve()
        staging = Path(staging_root).resolve()
        backup = Path(backup_root)
        applied, missing, errors = [], [], []
        for f in batch.files:
            rel = str(f["path"])
            src = (project / rel).resolve()
            staged = (staging / rel).resolve()
            if not str(staged).startswith(str(staging)):
                errors.append(f"staging 路径越界: {rel}")
                continue
            if not staged.is_file():
                missing.append(rel)
                continue
            if not str(src).startswith(str(project)):
                errors.append(f"工作区路径越界: {rel}")
                continue
            try:
                backup_path = backup / rel
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.copy2(src, backup_path)
                src.parent.mkdir(parents=True, exist_ok=True)
                tmp = src.with_name(src.name + ".flow-tmp")
                shutil.copy2(staged, tmp)
                tmp.replace(src)
                digest = hashlib.sha256(src.read_bytes()).hexdigest()
                self.store.set_item(batch.group_id, rel, status="applied",
                                    staged_path=str(staged), applied_hash=digest,
                                    evidence={"applied": True})
                applied.append(rel)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel}: {exc}")
        return {"batch_id": batch_id, "applied": applied, "missing": missing, "errors": errors}

    # ------------------------------------------------------------- helpers
    def close(self) -> None:
        self.store.close()


def plan_to_summary(plan: BatchPlan) -> Dict[str, Any]:
    return plan.to_dict()


def read_batch_files(path: str) -> List[Dict[str, Any]]:
    """从 JSON 文件读取文件清单（[{path,size,deps,risk}]）。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))
