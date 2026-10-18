"""异步质量任务：后台线程执行 build/browser，前端轮询 job 状态。"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


class QualityJobManager:
    def __init__(self, retention_seconds: float = 3600.0, max_jobs: int = 50):
        self.retention = float(retention_seconds)
        self.max_jobs = int(max_jobs)
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def _cleanup(self) -> None:
        now = time.time()
        stale = [jid for jid, j in self._jobs.items()
                 if j.get("status") != "running"
                 and now - float(j.get("finished_at") or j.get("started_at") or now) > self.retention]
        for jid in stale:
            self._jobs.pop(jid, None)
        if len(self._jobs) > self.max_jobs:
            done = sorted([j for j in self._jobs.values() if j.get("status") != "running"],
                          key=lambda x: x.get("started_at", 0))
            for j in done[:max(0, len(self._jobs) - self.max_jobs)]:
                self._jobs.pop(j["id"], None)

    def submit(self, fn: Callable[..., Any], *, kind: str = "quality",
               **kwargs: Any) -> Dict[str, Any]:
        jid = f"qj-{uuid.uuid4().hex[:12]}"
        job = {"id": jid, "kind": kind, "status": "running",
               "started_at": time.time(), "finished_at": None,
               "result": None, "error": ""}
        with self._lock:
            self._cleanup()
            self._jobs[jid] = job

        def worker() -> None:
            try:
                result = fn(**kwargs)
                with self._lock:
                    job["status"] = "done"
                    job["result"] = result
                    job["finished_at"] = time.time()
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    job["status"] = "error"
                    job["error"] = str(exc)
                    job["finished_at"] = time.time()

        threading.Thread(target=worker, name=f"flow-{jid}", daemon=True).start()
        return dict(job)

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.get("started_at", 0), reverse=True)
            return [dict(j) for j in jobs[:max(0, int(limit))]]


__all__ = ["QualityJobManager"]
