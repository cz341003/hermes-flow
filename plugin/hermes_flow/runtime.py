"""HERMES Flow 运行时：路径解析、Registry/Kernel/批次队列/经验库/运行记录。

独立于 Hermes 亦可工作（Dashboard backend 通过环境变量/默认路径初始化）；
在插件 ``register(ctx)`` 中会用 ctx 的 plugin_data_dir 精确配置。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches
from .flow_core.batch.driver import BatchAutoDriver
from .flow_core.batch.queue import plan_to_summary
from .flow_core.board import render_board
from .flow_core.experience import ExperienceBase
from .flow_core.kernel import Kernel
from .flow_core.quality.batch_gate import aggregate_gate, evaluate_batch
from .flow_core.registry import Registry

DEFAULT_HOME = Path(os.environ.get("HERMES_HOME") or r"E:\hermes")


def _now() -> int:
    return int(time.time())


def _safe_id(prefix: str = "run") -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


class FlowRuntime:
    def __init__(self, plugin_root: str | Path, data_dir: str | Path):
        self.plugin_root = Path(plugin_root).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._registry: Optional[Registry] = None
        self._kernel: Optional[Kernel] = None
        self._experience: Optional[ExperienceBase] = None
        self._batch_store: Optional[BatchStore] = None
        self._queue: Optional[BatchQueue] = None
        self._lifecycle: Any = None

    # ------------------------------------------------------------ properties
    @property
    def registry(self) -> Registry:
        with self._lock:
            if self._registry is None:
                self._registry = Registry(self.plugin_root, self.data_dir)
            return self._registry

    @property
    def kernel(self) -> Kernel:
        with self._lock:
            if self._kernel is None:
                self._kernel = Kernel(str(self.data_dir / "state.db"))
            return self._kernel

    @property
    def experience(self) -> ExperienceBase:
        with self._lock:
            if self._experience is None:
                self._experience = ExperienceBase(str(self.data_dir / "experience.db"))
            return self._experience

    @property
    def batch_store(self) -> BatchStore:
        with self._lock:
            if self._batch_store is None:
                self._batch_store = BatchStore(self.data_dir / "batches.db")
            return self._batch_store

    @property
    def queue(self) -> BatchQueue:
        with self._lock:
            if self._queue is None:
                self._queue = BatchQueue(self.batch_store)
            return self._queue

    def set_lifecycle(self, service: Any) -> None:
        """注入 ``ctx.subagent_lifecycle``（只在 Hermes turn 内可用）。"""
        self._lifecycle = service

    def auto_drive(self, *, group_id: str, max_batches: int = 1,
                   max_seconds: float = 240, apply: bool = True,
                   audit: bool = True, concurrency: Optional[int] = None,
                   quality: bool = False, browser: bool = False,
                   quality_timeout: int = 300,
                   owner: str = "hermes-flow-driver") -> Dict[str, Any]:
        """自动推进一个批次组：claim → 子代理 → 校验 → ingest/apply → 门控 → 下一批。"""
        if self._lifecycle is None:
            return {"ok": False, "driver_unavailable": True,
                    "error": "当前会话没有 subagent_lifecycle（必须在 Hermes agent turn 内调用）"}
        run = self._run_for_group(group_id)
        if run is None:
            raise KeyError(f"找不到批次组对应的 Run: {group_id}")
        node_id = next((n for n, g in (run.get("batch_groups") or {}).items() if g == group_id), "")
        wf = self.registry.get_workflow(run["workflow_id"])
        node = {}
        if wf:
            node = next((n for n in wf.definition.get("nodes", []) if n.get("id") == node_id), {})
        agent = self.registry.get_agent(str(node.get("agent", ""))) if node.get("agent") else None
        skills = []
        for sid in (agent.skills if agent else []):
            s = self.registry.get_skill(sid)
            if s:
                body = ""
                try:
                    if s.path:
                        body = Path(s.path).read_text(encoding="utf-8-sig")[:3500]
                except Exception:  # noqa: BLE001
                    body = s.description
                skills.append({"id": s.id, "name": s.name, "description": s.description,
                               "procedure": body})
        base_prompt = (
            f"你是 {(agent.name if agent else '代码迁移专家')}，负责一个批次的 Vue2→Vue3 迁移。\n"
            f"Run: {run['id']} / 节点: {node_id or 'transform'} / 批次: __BATCH_ID__\n"
            "要求：只修改批次文件清单内的文件；每个文件先读取 source_path，转换后写入 staging_path；"
            "不要修改工作区其它文件；不要安装/升级依赖。\n"
            "完成后只返回一个 JSON 对象（不要 Markdown）："
            '{"files":[{"path":"...","status":"done|failed","changes":"...","error":""}],'
            '"summary":"...","truncated":false,"score":90}'
        )
        if agent and agent.role:
            base_prompt = f"{agent.role}\n\n{base_prompt}"

        def build_prompt(batch, files):
            return base_prompt.replace("__BATCH_ID__", batch.id)

        def build_context(batch, files):
            experiences = []
            try:
                experiences = self.experience_search(query=node_id or "transform", limit=3)
            except Exception:  # noqa: BLE001
                pass
            payload = {
                "run_id": run["id"], "node_id": node_id, "batch_id": batch.id,
                "attempt": batch.attempt, "wave": batch.wave,
                "files": files,
                "skills": skills,
                "write_policy": {"mode": "staging_only",
                                 "note": "只写 staging_path；source_path 只读"},
                "experiences": experiences,
                "quality": {"target_score": 85, "rework_below": 70,
                            "hard_rules": ["JSON 可解析", "所有文件都有结果", "不越界写"]},
            }
            text = json.dumps(payload, ensure_ascii=False, indent=1)
            if len(text) > 30_000:
                text = text[:30_000] + "\n…(context truncated)"
            return text

        launcher = SubagentLifecycleLauncher(self._lifecycle)
        driver = BatchAutoDriver(
            self.queue, launcher,
            staging_base=self.data_dir / "staging",
            project_root=run.get("project_root", ""),
            build_prompt=build_prompt,
            build_context=build_context,
            lock_dir=self.data_dir / "driver-locks",
            owner=owner,
            audit=audit,
            audit_dir=self.data_dir / "audit",
            concurrency=concurrency,
            worktree_base=self.data_dir / "worktrees",
        )
        out = driver.drive(group_id, max_batches=max_batches,
                           max_seconds=max_seconds, apply=apply).to_dict()
        # 批次结束自动沉淀经验（失败/限流/截断/修复/越界）
        try:
            out["experiences_distilled"] = self.distill_batch_experiences(
                run["id"], node_id, out.get("events", []))
        except Exception:  # noqa: BLE001 - 记忆失败不影响批次
            out["experiences_distilled"] = 0
        # 记录到 Run trace + 持久化事件流（Dashboard 断线重放）
        run = self.get_run(run["id"]) or run
        run.setdefault("trace", []).append({"at": _now(), "driver": "auto",
                                            "group_id": group_id, **{k: out.get(k) for k in
                                                                      ("processed", "batches_done",
                                                                       "batches_total", "done", "error")}})
        self.record_event(run["id"], "driver", {k: out.get(k) for k in
                                                ("ok", "processed", "batches_done", "batches_total",
                                                 "done", "busy", "rate_limited",
                                                 "write_scope_violation", "error")})
        for item in out.get("events", []):
            self.record_event(run["id"], "batch_event", item)
        # 可选：批次全部完成后自动跑真实 build/typecheck/browser + 聚合门
        if quality and out.get("done"):
            try:
                scores = [float(b.score or 0) for b in self.queue.store.list_batches(group_id)
                          if b.status == "done"]
                q = self.quality_gate(project_root=run.get("project_root", ""),
                                      batch_scores=scores, coverage=1.0,
                                      browser=browser, timeout=quality_timeout)
                out["quality"] = q
                run["quality"] = q
                verdict = (q.get("aggregate") or {}).get("verdict", "")
                self.record_event(run["id"], "quality", {
                    "verdict": verdict,
                    "score": (q.get("aggregate") or {}).get("score")})
                if verdict != "pass":
                    out["quality_gate_failed"] = True
            except Exception as exc:  # noqa: BLE001 - 质量失败不丢批次结果
                out["quality_error"] = f"quality gate failed: {exc}"
                self.record_event(run["id"], "quality_error", {"error": str(exc)})
        if out.get("rate_limited"):
            run["status"] = "paused"
        elif out.get("write_scope_violation") or out.get("quality_gate_failed"):
            run["status"] = "gated"
        elif out.get("done"):
            run["status"] = "running"
        self.save_run(run)
        return out

    # ------------------------------------------------------------------ runs
    @property
    def runs_dir(self) -> Path:
        d = self.data_dir / "runs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _run_path(self, run_id: str) -> Path:
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in "-_")
        return self.runs_dir / f"{safe}.json"

    def save_run(self, run: Dict[str, Any]) -> None:
        run["updated_at"] = _now()
        with self._lock:
            self._run_path(run["id"]).write_text(
                json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self._run_path(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def record_event(self, run_id: str, event_type: str,
                     data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """持久化一条 Run 事件（seq 单调递增，供 Dashboard 断线重放）。"""
        run = self.get_run(run_id)
        if run is None:
            return None
        events = run.setdefault("events", [])
        seq = int(events[-1].get("seq", 0)) + 1 if events else 1
        event = {"seq": seq, "at": _now(), "type": event_type, "data": data or {}}
        events.append(event)
        if len(events) > 500:
            run["events"] = events[-500:]
        self.save_run(run)
        return event

    def run_events(self, run_id: str, after: int = 0) -> Dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"Run 不存在: {run_id}")
        events = [e for e in (run.get("events") or []) if int(e.get("seq", 0)) > int(after or 0)]
        last = max([int(e.get("seq", 0)) for e in (run.get("events") or [])] or [0])
        return {"run_id": run_id, "events": events, "last_seq": last,
                "run_status": run.get("status", "")}

    def gate_run(self, run_id: str, action: str, reason: str = "") -> Dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"Run 不存在: {run_id}")
        action = "approve" if action in ("approve", "approved", "pass") else "reject"
        if action == "reject":
            run["status"] = "cancelled"
        else:
            groups = run.get("batch_groups") or {}
            all_done = bool(groups) and all(
                self.batch_status(g).get("done_batches", 0) >= self.batch_status(g).get("total_batches", 1)
                for g in groups.values())
            run["status"] = "done" if all_done else "running"
        run.setdefault("gate_history", []).append({"at": _now(), "action": action, "reason": reason})
        self.save_run(run)
        self.record_event(run_id, f"gate_{action}", {"reason": reason,
                                                     "status": run["status"]})
        return {"run_id": run_id, "action": action, "status": run["status"], "reason": reason}

    def rerun_node(self, run_id: str, node_id: str) -> Dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"Run 不存在: {run_id}")
        group_id = (run.get("batch_groups") or {}).get(node_id)
        if not group_id:
            raise KeyError(f"节点没有批次组: {node_id}")
        count = self.queue.retry_failed(group_id)
        run["status"] = "running"
        self.save_run(run)
        self.record_event(run_id, "node_rerun", {"node_id": node_id,
                                                 "group_id": group_id, "retried": count})
        return {"run_id": run_id, "node_id": node_id, "group_id": group_id,
                "retried": count, "status": "running"}

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for path in sorted(self.runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
        return runs

    def start_run(self, *, workflow_id: str, project_root: str = "",
                  files: Optional[List[Dict[str, Any]]] = None,
                  title: str = "") -> Dict[str, Any]:
        wf = self.registry.get_workflow(workflow_id)
        if wf is None:
            raise KeyError(f"工作流不存在: {workflow_id}")
        files = list(files or [])
        run = {
            "id": _safe_id("run"),
            "workflow_id": workflow_id,
            "workflow_name": wf.name,
            "title": title or wf.name,
            "project_root": project_root,
            "files": files,
            "status": "queued",
            "created_at": _now(),
            "batch_groups": {},
            "node_states": {},
            "trace": [],
            "events": [{"seq": 1, "at": _now(), "type": "created",
                        "data": {"workflow_id": workflow_id, "files": len(files)}}],
            "gate_history": [],
            "report": {},
        }
        self.save_run(run)
        return run

    def update_run_status(self, run_id: str, status: str) -> Optional[Dict[str, Any]]:
        run = self.get_run(run_id)
        if run is None:
            return None
        run["status"] = status
        self.save_run(run)
        self.record_event(run_id, "status", {"status": status})
        return run

    # ---------------------------------------------------------------- batches
    def _run_for_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        for run in self.list_runs(limit=200):
            if group_id in (run.get("batch_groups") or {}).values():
                return run
        return None

    def batch_plan(self, *, run_id: str, node_id: str, files: Optional[List[Dict[str, Any]]] = None,
                   policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"Run 不存在: {run_id}")
        items = [FileItem.from_dict(f) for f in (files or run.get("files") or [])]
        if not items:
            raise ValueError("文件清单为空：请提供 files=[{path,size,deps}] 或先在 Run 中写入")
        wf = self.registry.get_workflow(run["workflow_id"])
        expert_id = ""
        expert_policy: Dict[str, Any] = {}
        if wf:
            for node in wf.definition.get("nodes", []):
                if node.get("id") == node_id:
                    expert_id = str(node.get("agent", ""))
                    break
            expert = self.registry.get_agent(expert_id) if expert_id else None
            if expert:
                expert_policy = dict(expert.loop_policy)
        pol = BatchPolicy.from_loop_policy({**expert_policy, **dict(policy or {})})
        plan = plan_batches(items, pol)
        group_id = f"g-{uuid.uuid4().hex[:10]}"
        self.queue.create_group(plan=plan, run_id=run_id, node_id=node_id,
                                expert_id=expert_id, policy=pol, group_id=group_id)
        run["batch_groups"][node_id] = group_id
        run["status"] = "running"
        self.save_run(run)
        self.record_event(run_id, "batch_plan", {
            "node_id": node_id, "group_id": group_id,
            "total_batches": plan_to_summary(plan).get("total_batches")})
        return {"run_id": run_id, "node_id": node_id, "group_id": group_id,
                "plan": plan_to_summary(plan)}

    def batch_next(self, *, group_id: str, owner: str = "agent") -> Dict[str, Any]:
        batch = self.queue.claim_next(group_id, owner)
        if batch is None:
            st = self.queue.status(group_id)
            done = st["done_batches"] >= st["total_batches"]
            return {"done": done, "group_id": group_id, "status": st}
        run = self._run_for_group(group_id)
        run_id = run["id"] if run else ""
        project_root = run.get("project_root", "") if run else ""
        staging_root = self.data_dir / "staging" / group_id / batch.id
        staging_root.mkdir(parents=True, exist_ok=True)
        files = []
        for f in batch.files:
            rel = f["path"]
            files.append({
                **f,
                "source_path": str(Path(project_root) / rel) if project_root else rel,
                "staging_path": str(staging_root / rel),
            })
        packet = {
            "run_id": run_id, "group_id": group_id, "batch_id": batch.id,
            "batch_index": batch.seq, "attempt": batch.attempt,
            "wave": batch.wave,
            "project_root": project_root,
            "staging_root": str(staging_root),
            "files": files,
            "order": [f["path"] for f in batch.files],
            "write_policy": {"mode": "staging_only", "forbidden": "project_root 下非 staging 路径"},
            "instruction": "读取 source_path，转换后写入 staging_path；不要修改工作区其他文件；"
                           "返回 JSON：{files:[{path,status,changes,notes,error}],summary,truncated}",
            "result_contract": {"format": "json", "max_chars": 24000},
        }
        if run_id:
            self.record_event(run_id, "batch_claimed", {
                "group_id": group_id, "batch_id": batch.id,
                "attempt": batch.attempt, "files": len(batch.files)})
        return packet

    def batch_status(self, group_id: str) -> Dict[str, Any]:
        return self.queue.status(group_id)

    def batch_items(self, batch_id: str) -> List[Dict[str, Any]]:
        return [i.to_dict() for i in self.queue.store.list_items(batch_id)]

    def batch_ingest(self, *, group_id: str, batch_id: str, results: List[Dict[str, Any]],
                     attempt_id: str = "", staging_root: str = "", project_root: str = "",
                     apply: bool = False, backup_root: str = "") -> Dict[str, Any]:
        out = self.queue.ingest(batch_id, results, attempt_id=attempt_id,
                                staging_root=staging_root or None,
                                project_root=project_root or None)
        if apply:
            if not staging_root or not project_root:
                out["apply_error"] = "apply 需要 staging_root 与 project_root"
            else:
                out["apply"] = self.queue.apply(
                    batch_id, project_root=project_root, staging_root=staging_root,
                    backup_root=backup_root or str(self.data_dir / "backups" / group_id / batch_id),
                )
        run = self._run_for_group(group_id)
        if run:
            self.record_event(run["id"], "batch_ingest", {
                "batch_id": batch_id, "results": len(results),
                "apply": bool(apply), "error": out.get("apply_error", "")})
        return out

    def batch_complete(self, batch_id: str, *, score: Optional[float] = None,
                       verdict: str = "pass") -> Dict[str, Any]:
        self.queue.complete(batch_id, score=score, verdict=verdict)
        batch = self.queue.store.get_batch(batch_id)
        if batch:
            run = self._run_for_group(batch.group_id)
            if run:
                self.record_event(run["id"], "batch_complete", {
                    "batch_id": batch_id, "score": score, "verdict": verdict})
        return {"batch_id": batch_id, "status": batch.status if batch else "unknown",
                "score": score, "verdict": verdict}

    def batch_fail(self, batch_id: str, reason: str = "") -> Dict[str, Any]:
        status = self.queue.fail(batch_id, reason)
        batch = self.queue.store.get_batch(batch_id)
        if batch:
            run = self._run_for_group(batch.group_id)
            if run:
                self.record_event(run["id"], "batch_fail", {
                    "batch_id": batch_id, "next_status": status, "reason": reason})
        return {"batch_id": batch_id, "next_status": status}

    def batch_split(self, batch_id: str) -> Dict[str, Any]:
        ids = self.queue.split(batch_id)
        batch = self.queue.store.get_batch(batch_id)
        if batch:
            run = self._run_for_group(batch.group_id)
            if run:
                self.record_event(run["id"], "batch_split", {
                    "batch_id": batch_id, "new_batches": ids})
        return {"batch_id": batch_id, "new_batches": ids}

    def batch_repair(self, batch_id: str, failed_files: List[str]) -> Dict[str, Any]:
        rid = self.queue.repair(batch_id, failed_files)
        batch = self.queue.store.get_batch(batch_id)
        if batch:
            run = self._run_for_group(batch.group_id)
            if run:
                self.record_event(run["id"], "batch_repair", {
                    "batch_id": batch_id, "repair_batch": rid,
                    "failed_files": len(failed_files)})
        return {"batch_id": batch_id, "repair_batch": rid}

    # ------------------------------------------------------------------ gate
    def gate_batch(self, *, ast_ok: bool, diff_ok: bool, write_scope_ok: bool = True,
                   scoped_tests_ok: bool = True, llm_score: Optional[float] = None,
                   truncated: bool = False) -> Dict[str, Any]:
        return evaluate_batch(ast_ok=ast_ok, diff_ok=diff_ok,
                              write_scope_ok=write_scope_ok,
                              scoped_tests_ok=scoped_tests_ok,
                              llm_score=llm_score, truncated=truncated)

    def quality_collect(self, *, project_root: str = "", build: bool = True,
                        typecheck: bool = True, tests: bool = False,
                        browser: bool = False, timeout: int = 300,
                        routes: Optional[List[str]] = None) -> Dict[str, Any]:
        from .flow_core.quality.collectors import collect
        root = project_root
        if not root:
            raise ValueError("quality_collect 需要 project_root（或先创建带 project_root 的 Run）")
        raw = collect(root, build=build, typecheck=typecheck, tests=tests,
                      browser=browser, timeout=timeout,
                      log_dir=self.data_dir / "quality", routes=routes)
        build_res = raw.get("build") or {}
        type_res = raw.get("typecheck") or {}
        browser_res = raw.get("browser") or {}
        build_ok = bool(build_res.get("ok"))
        type_ok = bool(type_res.get("ok") or type_res.get("skipped"))
        browser_checked = bool(browser_res.get("ran") and not browser_res.get("skipped"))
        raw["gate"] = {
            "full_build_ok": build_ok,
            "typecheck_ok": type_ok,
            "browser_ok": bool(browser_res.get("ok")) if browser_checked else False,
            "browser_checked": browser_checked,
        }
        return raw

    def quality_gate(self, *, project_root: str, batch_scores: List[float],
                     coverage: float = 1.0, browser: bool = False,
                     timeout: int = 300,
                     routes: Optional[List[str]] = None) -> Dict[str, Any]:
        raw = self.quality_collect(project_root=project_root, browser=browser,
                                   timeout=timeout, routes=routes)
        gate = self.gate_aggregate(batch_scores=batch_scores, coverage=coverage,
                                   full_build_ok=bool(raw["gate"]["full_build_ok"]),
                                   browser_ok=bool(raw["gate"]["browser_ok"]))
        return {"collect": raw, "aggregate": gate}

    def gate_aggregate(self, *, batch_scores: List[float], coverage: float,
                       full_build_ok: bool, browser_ok: bool) -> Dict[str, Any]:
        return aggregate_gate(batch_scores=batch_scores, coverage=coverage,
                              full_build_ok=full_build_ok, browser_ok=browser_ok)

    # ------------------------------------------------------------ experience
    def experience_add(self, *, category: str, trigger: str, solution: str,
                       phase: str = "", stack: Optional[Dict[str, Any]] = None,
                       versions: str = "") -> Dict[str, Any]:
        from dataclasses import asdict
        e = self.experience.record(category, trigger, solution,
                                   versions=versions or None)
        data = asdict(e)
        if phase:
            data["phase"] = phase
        return data

    def experience_search(self, *, query: str = "", phase: str = "",
                          limit: int = 5) -> List[Dict[str, Any]]:
        from dataclasses import asdict
        rows = self.experience.recall(phase=phase or None,
                                      context=query or "", limit=limit)
        return [asdict(r) for r in rows]

    def distill_batch_experiences(self, run_id: str, node_id: str,
                                  events: List[Dict[str, Any]]) -> int:
        """把 driver 批次失败/恢复动作自动沉淀为经验卡（去重由经验库负责）。"""
        from .flow_core.recovery import classify
        added = 0
        for ev in events or []:
            action = str(ev.get("action") or "")
            error = str(ev.get("error") or "")
            if action not in ("failed", "drift", "rate_limited", "split", "repair"):
                continue
            category = "migration_failure"
            solution = ""
            if action == "drift" or "FLOW_BATCH_WRITE_SCOPE" in error:
                category = "write_scope"
                solution = ("子代理写了批次外文件，driver 已回滚并置 Run gated。"
                            "经验：只允许写 staging_path；批外写入会被审计拒绝。")
            elif action == "rate_limited":
                category = "rate_limit"
                solution = "429 限流时 driver 会 requeue 且不消耗 attempt；稍后重试同一 group，不要重建批次。"
            elif action == "split" or "truncat" in error.lower():
                category = "truncation"
                solution = "子代理输出截断，driver 已二分拆批。经验：控制单批文件数/结果 JSON 大小，优先小批。"
            elif action == "repair":
                category = "quality_rework"
                solution = "批次低分/失败，driver 已创建 repair 子批。经验：只修复失败文件，避免整批重写。"
            else:
                cat = classify(error)
                category = cat.value if cat.value != "unknown" else "migration_failure"
                solution = f"批次失败：{error[:200]}。检查该批文件与子代理输出后再重跑。"
            trigger = f"{node_id}:{action}:{error[:120]}"
            try:
                self.experience.record(category, trigger, solution, versions="")
                added += 1
            except Exception:  # noqa: BLE001
                continue
        if added:
            self.record_event(run_id, "memory_distilled", {"node_id": node_id, "count": added})
        return added

    # ----------------------------------------------------------------- board
    def render_board(self, *, title: str = "HERMES Flow 迁移看板", out: str = "") -> str:
        runs = self.list_runs(limit=10)
        workflows = [{"id": r["id"], "name": r.get("title", r["id"]),
                      "states": r.get("node_states", {}), "done": r.get("status") == "done"}
                     for r in runs]
        experiences = self.experience_search(limit=10)
        html = render_board(workflows, experiences, title=title)
        if out:
            path = Path(out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
        return html

    # ---------------------------------------------------------------- status
    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "version": "0.2.0",
            "home": str(DEFAULT_HOME),
            "data_dir": str(self.data_dir),
            "agents": len(self.registry.list_agents()),
            "skills": len(self.registry.list_skills()),
            "workflows": len(self.registry.list_workflows()),
            "runs": [{
                "id": r["id"], "status": r.get("status"), "title": r.get("title"),
                "workflow_id": r.get("workflow_id"),
                "project_root": r.get("project_root", ""),
                "created_at": r.get("created_at", 0),
                "batch_groups": r.get("batch_groups", {}),
            } for r in self.list_runs()],
            "errors": self.registry.last_errors,
        }

    # ------------------------------------------------------------ lifecycle
    def close(self) -> None:
        if self._batch_store:
            self._batch_store.close()


class SubagentLifecycleLauncher:
    """把 Hermes ``ctx.subagent_lifecycle`` 适配成 driver 需要的四个方法。"""

    def __init__(self, service: Any):
        self.service = service

    def launch(self, *, goal: str, context: str, metadata: Dict[str, Any],
               correlation_id: str) -> Dict[str, Any]:
        # 传 mapping 即可：Hermes 的 launch 同时接受 SubagentLaunchRequest 和 mapping，
        # 这样 driver 在无 Hermes 环境也可单测。
        request = {
            "goal": goal[:15_500], "context": (context or "")[:31_000],
            "role": "leaf", "correlation_id": correlation_id,
            "metadata": {k: v for k, v in metadata.items() if k != "files"},
        }
        return self.service.launch(request).to_dict()

    def wait(self, handle: Any, *, timeout: float) -> Dict[str, Any]:
        terminal = self.service.wait(handle, timeout_seconds=timeout)
        return {
            "completed": bool(getattr(terminal, "completed", False)),
            "timed_out": bool(getattr(terminal, "timed_out", False)),
            "state": getattr(getattr(terminal, "state", None), "value",
                             str(getattr(terminal, "state", ""))),
        }

    def result(self, handle: Any) -> Dict[str, Any]:
        result = self.service.result(handle)
        return {
            "terminal_state": getattr(getattr(result, "terminal_state", None), "value",
                                      str(getattr(result, "terminal_state", ""))),
            "summary": getattr(result, "summary", None),
            "error_message": getattr(result, "error_message", None),
            "error_classification": getattr(result, "error_classification", None),
        }

    def cancel(self, handle: Any, *, reason: str) -> Any:
        return self.service.cancel(handle, reason=reason)


_runtime: Optional[FlowRuntime] = None
_runtime_lock = threading.Lock()


def configure(*, plugin_root: str | Path, data_dir: str | Path) -> FlowRuntime:
    global _runtime
    with _runtime_lock:
        _runtime = FlowRuntime(plugin_root, data_dir)
        return _runtime


def get_runtime() -> FlowRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            plugin_root = Path(__file__).resolve().parent
            home = Path(os.environ.get("HERMES_HOME") or DEFAULT_HOME)
            _runtime = FlowRuntime(plugin_root, home / "plugin-data" / "hermes_flow")
        return _runtime
