"""批次自动 driver：claim → 启动子代理 → 等待/校验 → ingest/apply → 质量门 → complete。

与 Hermes 解耦：launcher 只需实现 launch/wait/result/cancel 四个方法；
生产环境由 ``SubagentLifecycleLauncher`` 包装 ``ctx.subagent_lifecycle``。
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import BatchPolicy, BatchRecord
from .queue import BatchQueue
from .audit import WorkspaceAudit
from ..quality.batch_gate import evaluate_batch
from ..recovery import classify


class DriverBusy(RuntimeError):
    """同一 group 已有活跃 driver。"""


class DriverUnavailable(RuntimeError):
    """当前 turn 没有可用的子代理生命周期服务。"""


@dataclass
class DriveEvent:
    batch_id: str
    attempt: int
    action: str
    state: str = ""
    score: Optional[float] = None
    files_done: int = 0
    files_failed: int = 0
    error: str = ""
    child_id: str = ""
    elapsed: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id, "attempt": self.attempt, "action": self.action,
            "state": self.state, "score": self.score, "files_done": self.files_done,
            "files_failed": self.files_failed, "error": self.error,
            "child_id": self.child_id, "elapsed": round(self.elapsed, 3),
        }


@dataclass
class DriveResult:
    ok: bool
    driver: str = "flow"
    group_id: str = ""
    processed: int = 0
    batches_done: int = 0
    batches_total: int = 0
    done: bool = False
    busy: bool = False
    rate_limited: bool = False
    retry_after: int = 0
    driver_unavailable: bool = False
    write_scope_violation: bool = False
    events: List[DriveEvent] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "driver": self.driver, "group_id": self.group_id,
            "processed": self.processed, "batches_done": self.batches_done,
            "batches_total": self.batches_total, "done": self.done,
            "busy": self.busy, "rate_limited": self.rate_limited,
            "retry_after": self.retry_after,
            "driver_unavailable": self.driver_unavailable,
            "write_scope_violation": self.write_scope_violation,
            "events": [e.to_dict() for e in self.events], "error": self.error,
        }


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_child_summary(summary: Optional[str]) -> Optional[Dict[str, Any]]:
    """从子代理最终 summary 中提取结果 JSON；容忍 ```json 围栏与前后说明。"""
    if not summary:
        return None
    text = summary.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    for candidate in (text,):
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except Exception:  # noqa: BLE001
            pass
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        value = json.loads(m.group(0))
        return value if isinstance(value, dict) else None
    except Exception:  # noqa: BLE001
        return None


def normalize_files(result: Dict[str, Any], expected: List[str]) -> Dict[str, Dict[str, Any]]:
    """把子代理返回的 files 规范化成 {path: {status,error,changes}}，缺失文件记为 failed。"""
    out: Dict[str, Dict[str, Any]] = {}
    raw = result.get("files")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("file") or "").replace("\\", "/")
            if not path:
                continue
            status = str(item.get("status") or item.get("result") or "").lower()
            ok = status in ("done", "ok", "success", "successful", "converted", "applied")
            if status in ("failed", "error", "skipped"):
                ok = False
            out[path] = {
                "status": "done" if ok else "failed",
                "error": str(item.get("error") or ""),
                "changes": str(item.get("changes") or item.get("notes") or "")[:2000],
            }
    for path in expected:
        out.setdefault(path, {"status": "failed", "error": "missing from child result", "changes": ""})
    return out


class FileLock:
    """跨进程 driver 单例锁；进程崩溃后由 TTL 接管。"""

    def __init__(self, lock_dir: str | Path, group_id: str, ttl_seconds: float = 1800):
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in group_id)
        self.path = self.lock_dir / f"{safe}.lock"
        self.ttl = max(1, int(ttl_seconds))
        self.acquired = False

    def _write(self) -> None:
        payload = json.dumps({"pid": os.getpid(), "at": time.time(), "group": self.path.stem})
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(payload)

    def acquire(self) -> bool:
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"pid": os.getpid(), "at": time.time(), "group": self.path.stem}))
            self.acquired = True
            return True
        except FileExistsError:
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                age = self.ttl + 1
            if age > self.ttl:
                try:
                    self.path.unlink()
                except OSError:
                    return False
                return self.acquire()
            return False

    def touch(self) -> None:
        """心跳：driver 存活时刷新锁龄，避免长批次被误判为 stale。"""
        if self.acquired:
            try:
                self._write()
            except OSError:
                pass

    def release(self) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass
            self.acquired = False


class BatchAutoDriver:
    """单个 group 的同步 driver；每次调用最多处理 max_batches 批 / max_seconds 秒。"""

    def __init__(
        self, queue: BatchQueue, launcher: Any,
        *, staging_base: str | Path, project_root: str = "",
        build_prompt: Optional[Callable[[BatchRecord, List[Dict[str, Any]]], str]] = None,
        build_context: Optional[Callable[[BatchRecord, List[Dict[str, Any]]], str]] = None,
        lock_dir: Optional[str | Path] = None,
        owner: str = "flow-driver",
        audit: bool = True,
        audit_dir: Optional[str | Path] = None,
        concurrency: Optional[int] = None,
        worktree_base: Optional[str | Path] = None,
        lock_ttl_seconds: Optional[float] = None,
    ):
        self.queue = queue
        self.launcher = launcher
        self.staging_base = Path(staging_base)
        self.project_root = project_root
        self.build_prompt = build_prompt or self._default_prompt
        self.build_context = build_context or self._default_context
        self.lock_dir = Path(lock_dir) if lock_dir else Path(staging_base).parent / "driver-locks"
        self.owner = owner
        self.audit_enabled = audit and bool(project_root)
        self.audit_dir = Path(audit_dir) if audit_dir else Path(staging_base).parent / "audit"
        self._audit: Optional[WorkspaceAudit] = None
        self._allowed_paths: List[str] = []
        self.concurrency = concurrency
        self.worktree_base = (Path(worktree_base) if worktree_base
                              else Path(staging_base).parent / "worktrees")
        self.lock_ttl_seconds = lock_ttl_seconds

    # ------------------------------------------------------------------ public
    def drive(self, group_id: str, *, max_batches: int = 1, max_seconds: float = 240,
              apply: bool = True, poll_slice: float = 10.0) -> DriveResult:
        # Hermes 单次工具调用硬上限 420s；driver 必须在其之前返回，否则会留下
        # 仍在运行的线程与未被正常释放的锁。默认 240s，硬上限 360s。
        max_seconds = min(360.0, max(30.0, float(max_seconds)))
        lock = FileLock(self.lock_dir, group_id,
                        ttl_seconds=self.lock_ttl_seconds or max(120, min(420, max_seconds + 60)))
        if not lock.acquire():
            status = self.queue.status(group_id)
            return DriveResult(ok=False, group_id=group_id, busy=True,
                               batches_done=status["done_batches"],
                               batches_total=status["total_batches"],
                               error="另一个 driver 正在推进该批次组")
        deadline = time.time() + max(1.0, float(max_seconds))
        result = DriveResult(ok=True, group_id=group_id)
        if self.audit_enabled:
            try:
                self._audit = WorkspaceAudit(self.project_root,
                                             Path(self.audit_dir) / group_id)
                self._audit.ensure_baseline()
                self._allowed_paths = [f["path"] for b in self.queue.store.list_batches(group_id)
                                       for f in b.files]
            except Exception as exc:  # noqa: BLE001
                result.error = f"workspace audit disabled: {exc}"
                self._audit = None
        try:
            policy = self.queue.policy_for(group_id)
            concurrency = self.concurrency or policy.max_concurrent_batches or 1
            concurrency = max(1, min(3, int(concurrency)))
            processed = 0
            while processed < max(1, int(max_batches)) and time.time() < deadline:
                lock.touch()
                if concurrency > 1:
                    batches = []
                    for _ in range(min(concurrency, max(1, int(max_batches)) - processed)):
                        b = self.queue.claim_next(group_id, self.owner,
                                                  max_concurrent=concurrency)
                        if b is None:
                            break
                        batches.append(b)
                    if not batches:
                        break
                    events = self._run_parallel(batches, deadline, apply=apply,
                                                poll_slice=poll_slice)
                else:
                    batch = self.queue.claim_next(group_id, self.owner,
                                                  max_concurrent=1 if concurrency == 1 else concurrency)
                    if batch is None:
                        break
                    started = time.time()
                    event = self._run_one(batch, deadline, apply=apply, poll_slice=poll_slice)
                    event.elapsed = time.time() - started
                    events = [event]
                stop = False
                for event in events:
                    result.events.append(event)
                    lock.touch()
                    if event.action == "drift":
                        result.ok = False
                        result.write_scope_violation = True
                        result.error = event.error
                        stop = True
                        break
                    if event.action in ("rate_limited", "driver_unavailable"):
                        result.ok = False
                        result.rate_limited = event.action == "rate_limited"
                        result.driver_unavailable = event.action == "driver_unavailable"
                        result.retry_after = 60 if result.rate_limited else 0
                        stop = True
                        break
                    if event.action in ("done", "split", "repair", "failed"):
                        processed += 1
                        if event.action == "done":
                            result.batches_done += 1
                if stop:
                    break
            status = self.queue.status(group_id)
            result.batches_done = status["done_batches"]
            result.batches_total = status["total_batches"]
            result.done = (status["done_batches"] >= status["total_batches"]
                           and not status["running"] and not status["failed"])
            result.processed = processed
            return result
        finally:
            lock.release()

    # ------------------------------------------------------------------ batch
    def _prepare(self, batch: BatchRecord, isolate: bool = False):
        files = self._files(batch, isolate=isolate)
        prompt = self.build_prompt(batch, files)
        context = self.build_context(batch, files)
        metadata = {
            "kind": "hermes_flow.batch", "batch_id": batch.id, "group_id": batch.group_id,
            "attempt": batch.attempt, "isolated": isolate,
            "files": [f["staging_path"] for f in files],
        }
        return files, prompt, context, metadata

    def _run_one(self, batch: BatchRecord, deadline: float, *, apply: bool,
                 poll_slice: float) -> DriveEvent:
        files, prompt, context, metadata = self._prepare(batch)
        outcome = self._execute(batch, prompt, context, metadata, deadline, poll_slice)
        return self._commit(batch, files, outcome, apply)

    def _run_parallel(self, batches: List[BatchRecord], deadline: float, *,
                      apply: bool, poll_slice: float) -> List[DriveEvent]:
        """同 wave 并行：子代理并跑，提交/apply 按 batch seq 稳定顺序串行。"""
        prepared = [self._prepare(b, isolate=True) for b in batches]
        outcomes: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(batches),
                                thread_name_prefix="flow-batch") as pool:
            futures = {}
            for batch, (files, prompt, context, metadata) in zip(batches, prepared):
                # Hermes 的 parent session 存在 contextvar 中；线程池默认不继承，
                # 必须为每个 worker 复制当前 context，否则 lifecycle.launch 会报
                # "No active Hermes parent session"。
                worker_ctx = contextvars.copy_context()
                futures[pool.submit(worker_ctx.run, self._execute, batch, prompt,
                                    context, metadata, deadline, poll_slice)] = batch.id
            for future in futures:
                try:
                    outcomes[futures[future]] = future.result()
                except Exception as exc:  # noqa: BLE001
                    outcomes[futures[future]] = {"action": "failed",
                                                 "error": f"parallel worker: {exc}"}
        events = []
        for batch, (files, _prompt, _context, _metadata) in zip(batches, prepared):
            events.append(self._commit(batch, files, outcomes.get(batch.id, {}), apply))
        return events

    def _commit(self, batch: BatchRecord, files: List[Dict[str, Any]],
                outcome: Dict[str, Any], apply: bool) -> DriveEvent:
        if outcome.get("action") == "rate_limited":
            self.queue.requeue(batch.id, "429 rate limited (driver)")
            return DriveEvent(batch.id, batch.attempt, "rate_limited",
                              error=str(outcome.get("error") or ""))
        if outcome.get("action") == "driver_unavailable":
            self.queue.requeue(batch.id, "no active parent session")
            return DriveEvent(batch.id, batch.attempt, "driver_unavailable",
                              error=str(outcome.get("error") or ""))
        if outcome.get("action") == "split":
            return DriveEvent(batch.id, batch.attempt, "split", files_failed=1,
                              child_id=str(outcome.get("child_id") or ""))
        if outcome.get("action") == "failed":
            self.queue.fail(batch.id, str(outcome.get("error") or "batch failed"))
            return DriveEvent(batch.id, batch.attempt, "failed",
                              error=str(outcome.get("error") or ""),
                              child_id=str(outcome.get("child_id") or ""))
        parsed = outcome.get("parsed") or {}
        normalized = normalize_files(parsed, [f["path"] for f in files])
        done = [p for p, v in normalized.items() if v["status"] == "done"]
        failed = [p for p, v in normalized.items() if v["status"] != "done"]
        results = []
        for path, info in normalized.items():
            staging = next((f["staging_path"] for f in files if f["path"] == path), "")
            results.append({"path": path, "status": info["status"], "staged_path": staging,
                            "error": info["error"]})
        try:
            self.queue.ingest(batch.id, results, attempt_id=str(batch.attempt))
        except Exception as exc:  # noqa: BLE001
            return DriveEvent(batch.id, batch.attempt, "failed", error=f"ingest failed: {exc}")
        if apply and done:
            try:
                applied = self.queue.apply(
                    batch.id, project_root=self.project_root,
                    staging_root=str(self.staging_base / batch.group_id / batch.id),
                    backup_root=str(self.staging_base.parent / "backups" / batch.group_id / batch.id))
                if applied.get("errors"):
                    return DriveEvent(batch.id, batch.attempt, "failed",
                                      files_done=len(done), files_failed=len(failed),
                                      error=f"apply errors: {applied['errors'][:3]}")
            except Exception as exc:  # noqa: BLE001
                return DriveEvent(batch.id, batch.attempt, "failed",
                                  files_done=len(done), files_failed=len(failed),
                                  error=f"apply failed: {exc}")
            if self._audit is not None:
                report = self._audit.audit(self._allowed_paths)
                if not report.get("ok"):
                    detail = "; ".join(f"{v['kind']}:{v['path']}" for v in report.get("violations", [])[:5])
                    self.queue.fail(batch.id, f"FLOW_BATCH_WRITE_SCOPE {detail}")
                    return DriveEvent(batch.id, batch.attempt, "drift",
                                      files_done=len(done), files_failed=len(failed),
                                      error=f"FLOW_BATCH_WRITE_SCOPE: {detail}")
        ast_ok = bool(parsed) and not failed
        score = _as_float(parsed.get("score"))
        if score is None:
            score = 90.0 if done and not failed else 60.0
        gate = evaluate_batch(ast_ok=ast_ok, diff_ok=bool(done),
                              write_scope_ok=True, scoped_tests_ok=True,
                              llm_score=score, truncated=bool(parsed.get("truncated")))
        if gate.get("hard_fail") or gate.get("score", 0) < 70:
            repair = self.queue.repair(batch.id, failed or [f["path"] for f in files])
            self.queue.complete(batch.id, score=gate.get("score"), verdict="rework")
            return DriveEvent(batch.id, batch.attempt, "repair" if repair else "failed",
                              score=gate.get("score"), files_done=len(done),
                              files_failed=len(failed),
                              error="" if repair else "batch gate failed and repair exhausted")
        self.queue.complete(batch.id, score=gate.get("score"),
                            verdict="pass" if gate.get("score", 0) >= 85 else "warn")
        return DriveEvent(batch.id, batch.attempt, "done", score=gate.get("score"),
                          files_done=len(done), files_failed=len(failed),
                          child_id=str(outcome.get("child_id") or ""))

    def _execute(self, batch: BatchRecord, prompt: str, context: str,
                 metadata: Dict[str, Any], deadline: float, poll_slice: float) -> Dict[str, Any]:
        try:
            handle = self.launcher.launch(goal=prompt, context=context,
                                          metadata=metadata,
                                          correlation_id=f"flow-{batch.group_id}-{batch.id}-{batch.attempt}")
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if "No active Hermes parent" in text:
                return {"action": "driver_unavailable", "error": text}
            return {"action": "failed", "error": f"launch failed: {text}"}
        child_id = _handle_id(handle)
        try:
            terminal = self.launcher.wait(handle, timeout=min(30.0, max(1.0, deadline - time.time())))
        except Exception as exc:  # noqa: BLE001
            return {"action": "failed", "error": f"wait failed: {exc}", "child_id": child_id}
        while not _terminal_done(terminal):
            if time.time() >= deadline:
                try:
                    self.launcher.cancel(handle, reason="flow driver deadline")
                except Exception:  # noqa: BLE001
                    pass
                return {"action": "failed", "error": "child timeout", "child_id": child_id}
            try:
                terminal = self.launcher.wait(
                    handle, timeout=min(max(1.0, poll_slice), max(1.0, deadline - time.time())))
            except Exception as exc:  # noqa: BLE001
                return {"action": "failed", "error": f"wait failed: {exc}", "child_id": child_id}
        try:
            res = self.launcher.result(handle)
        except Exception as exc:  # noqa: BLE001
            return {"action": "failed", "error": f"result failed: {exc}", "child_id": child_id}
        state = str(_get(res, "terminal_state") or _get(res, "state") or "").upper()
        if state not in ("SUCCEEDED", "COMPLETED"):
            err = str(_get(res, "error_message") or _get(res, "error_classification") or state)
            category = classify(err).value
            if category == "rate_limit":
                return {"action": "rate_limited", "error": err, "child_id": child_id}
            if "truncat" in err.lower():
                ids = self.queue.split(batch.id)
                return {"action": "split" if ids else "failed", "error": err, "child_id": child_id}
            return {"action": "failed", "error": err, "child_id": child_id}
        summary = _get(res, "summary")
        parsed = parse_child_summary(summary)
        if parsed is None:
            # B13：一次格式纠正重派
            correction = context + "\n\n上一次输出不是合法 JSON。请只输出 JSON 对象，不要 Markdown。"
            try:
                handle2 = self.launcher.launch(goal=prompt, context=correction,
                                               metadata={**metadata, "correction": True},
                                               correlation_id=f"flow-{batch.id}-{batch.attempt}-fix")
            except Exception as exc:  # noqa: BLE001
                return {"action": "failed", "error": f"corrective launch failed: {exc}"}
            child_id = _handle_id(handle2)
            terminal = self.launcher.wait(handle2, timeout=min(30.0, max(1.0, deadline - time.time())))
            while not _terminal_done(terminal):
                if time.time() >= deadline:
                    try:
                        self.launcher.cancel(handle2, reason="flow driver deadline")
                    except Exception:  # noqa: BLE001
                        pass
                    return {"action": "failed", "error": "corrective child timeout", "child_id": child_id}
                terminal = self.launcher.wait(handle2, timeout=min(max(1.0, poll_slice), 30.0))
            res2 = self.launcher.result(handle2)
            parsed = parse_child_summary(_get(res2, "summary"))
            if parsed is None:
                return {"action": "failed", "error": "invalid JSON after corrective attempt",
                        "child_id": child_id}
        return {"action": "ok", "parsed": parsed, "child_id": child_id}

    # ------------------------------------------------------------------ helpers
    def _files(self, batch: BatchRecord, isolate: bool = False) -> List[Dict[str, Any]]:
        root = self.staging_base / batch.group_id / batch.id
        out = []
        for f in batch.files:
            rel = f["path"]
            source = Path(self.project_root) / rel if self.project_root else Path(rel)
            if isolate and self.project_root:
                wt = self.worktree_base / batch.group_id / batch.id / rel
                try:
                    if source.is_file():
                        wt.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, wt)
                        source = wt
                except OSError:
                    pass
            out.append({
                **f,
                "source_path": str(source),
                "staging_path": str(root / rel),
            })
        return out

    @staticmethod
    def _default_prompt(batch: BatchRecord, files: List[Dict[str, Any]]) -> str:
        return "按批次逐文件完成迁移，只写 staging 路径，最后只返回 JSON。"

    @staticmethod
    def _default_context(batch: BatchRecord, files: List[Dict[str, Any]]) -> str:
        return json.dumps({"batch_id": batch.id, "files": files}, ensure_ascii=False)


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _handle_id(handle: Any) -> str:
    return str(_get(handle, "subagent_id") or _get(handle, "id") or "")


def _terminal_done(terminal: Any) -> bool:
    if terminal is None:
        return False
    if isinstance(terminal, dict):
        if terminal.get("timed_out"):
            return False
        return bool(terminal.get("completed")) or str(terminal.get("state") or "").upper() in (
            "SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED")
    if getattr(terminal, "timed_out", False):
        return False
    return bool(getattr(terminal, "completed", False)) or str(
        getattr(terminal, "state", "")).upper().endswith(("SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"))
