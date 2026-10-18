"""Dashboard 后端（FastAPI router），挂载到 ``/api/plugins/hermes_flow/``。

Hermes 在 web server 启动/首次请求时导入本文件并读取模块级 ``router``；
因此这里用 importlib 以包方式加载插件根目录，避免相对导入失败。
"""
from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
_PKG = "hermes_flow_runtime_pkg"
if _PKG not in sys.modules:
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(ROOT)]  # type: ignore[attr-defined]
    sys.modules[_PKG] = pkg

from hermes_flow_runtime_pkg.runtime import get_runtime  # noqa: E402
from hermes_flow_runtime_pkg.flow_core.quality.jobs import QualityJobManager  # noqa: E402

router = APIRouter()
_QUALITY_JOBS = QualityJobManager()


def _rt():
    return get_runtime()


class AgentBody(BaseModel):
    name: str
    role: str
    description: str = ""
    skills: List[str] = []
    model: str = ""
    toolsets: List[str] = []
    loop_policy: Dict[str, Any] = {}


class SkillBody(BaseModel):
    name: str
    description: str
    body: str
    phases: List[str] = []
    tags: List[str] = []


class WorkflowBody(BaseModel):
    definition: Dict[str, Any]


class RunBody(BaseModel):
    workflow_id: str
    project_root: str = ""
    files: List[Dict[str, Any]] = []
    title: str = ""


class BatchIngestBody(BaseModel):
    results: List[Dict[str, Any]]
    attempt_id: str = ""
    staging_root: str = ""
    project_root: str = ""
    apply: bool = False


class ClaimBody(BaseModel):
    group_id: str
    owner: str = "agent"


@router.get("/status")
def status() -> Dict[str, Any]:
    return _rt().status()


@router.get("/diagnostics")
def diagnostics() -> Dict[str, Any]:
    rt = _rt()
    return {"ok": True, "data_dir": str(rt.data_dir), "plugin_root": str(rt.plugin_root),
            "registry_errors": rt.registry.last_errors,
            "runs": len(rt.list_runs(limit=100))}


# ------------------------------------------------------------------ agents
@router.get("/agents")
def list_agents() -> Dict[str, Any]:
    return {"agents": [a.to_dict() for a in _rt().registry.list_agents()]}


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> Dict[str, Any]:
    a = _rt().registry.get_agent(agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    return a.to_dict()


@router.post("/agents")
def create_agent(body: AgentBody) -> Dict[str, Any]:
    try:
        return _rt().registry.create_agent(body.model_dump()).to_dict()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str) -> Dict[str, Any]:
    try:
        return {"deleted": _rt().registry.delete_agent(agent_id)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


# ------------------------------------------------------------------ skills
@router.get("/skills")
def list_skills() -> Dict[str, Any]:
    return {"skills": [s.to_dict() for s in _rt().registry.list_skills()]}


@router.post("/skills")
def create_skill(body: SkillBody) -> Dict[str, Any]:
    try:
        return _rt().registry.create_skill(body.name, body.description, body.body,
                                           phases=body.phases, tags=body.tags).to_dict()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str) -> Dict[str, Any]:
    s = _rt().registry.get_skill(skill_id)
    if s is None:
        raise HTTPException(404, "skill not found")
    out = s.to_dict()
    try:
        if s.path:
            out["content"] = Path(s.path).read_text(encoding="utf-8-sig")
    except Exception:  # noqa: BLE001
        out["content"] = ""
    return out


# --------------------------------------------------------------- workflows
@router.get("/workflows")
def list_workflows() -> Dict[str, Any]:
    return {"workflows": [{k: v for k, v in w.to_dict().items() if k != "definition"}
                          for w in _rt().registry.list_workflows()]}


@router.post("/workflows")
def create_workflow(body: WorkflowBody) -> Dict[str, Any]:
    try:
        return _rt().registry.save_workflow(body.definition).to_dict()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> Dict[str, Any]:
    wf = _rt().registry.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    return wf.to_dict()


# -------------------------------------------------------------------- runs
@router.get("/runs")
def list_runs() -> Dict[str, Any]:
    return {"runs": _rt().list_runs()}


@router.post("/runs")
def create_run(body: RunBody) -> Dict[str, Any]:
    try:
        return _rt().start_run(workflow_id=body.workflow_id, project_root=body.project_root,
                               files=body.files, title=body.title)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    run = _rt().get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    groups = {}
    for node, gid in (run.get("batch_groups") or {}).items():
        groups[node] = _rt().batch_status(gid)
    out = dict(run)
    out["batches"] = groups
    wf = _rt().registry.get_workflow(run.get("workflow_id", ""))
    out["workflow"] = wf.definition if wf else {}
    return out


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: str) -> Dict[str, Any]:
    run = _rt().update_run_status(run_id, "paused")
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str) -> Dict[str, Any]:
    run = _rt().update_run_status(run_id, "running")
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> Dict[str, Any]:
    run = _rt().update_run_status(run_id, "cancelled")
    if run is None:
        raise HTTPException(404, "run not found")
    return run


# ----------------------------------------------------------------- batches
@router.post("/batches/claim")
def claim_batch(body: ClaimBody) -> Dict[str, Any]:
    try:
        return {"packet": _rt().batch_next(group_id=body.group_id, owner=body.owner)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/groups/{group_id}")
def group_status(group_id: str) -> Dict[str, Any]:
    return _rt().batch_status(group_id)


@router.get("/batches/{batch_id}/items")
def batch_items(batch_id: str) -> Dict[str, Any]:
    return {"batch_id": batch_id, "items": _rt().batch_items(batch_id)}


@router.post("/batches/{batch_id}/ingest")
def ingest_batch(batch_id: str, body: BatchIngestBody) -> Dict[str, Any]:
    group = _rt().queue.store.get_batch(batch_id)
    if group is None:
        raise HTTPException(404, "batch not found")
    return _rt().batch_ingest(group_id=group.group_id, batch_id=batch_id,
                              results=body.results, attempt_id=body.attempt_id,
                              staging_root=body.staging_root, project_root=body.project_root,
                              apply=body.apply)


@router.post("/batches/{batch_id}/complete")
def complete_batch(batch_id: str, score: Optional[float] = None, verdict: str = "pass") -> Dict[str, Any]:
    return _rt().batch_complete(batch_id, score=score, verdict=verdict)


@router.post("/batches/{batch_id}/fail")
def fail_batch(batch_id: str, reason: str = "") -> Dict[str, Any]:
    return _rt().batch_fail(batch_id, reason)


@router.post("/batches/{batch_id}/split")
def split_batch(batch_id: str) -> Dict[str, Any]:
    return _rt().batch_split(batch_id)


@router.post("/batches/{batch_id}/repair")
def repair_batch(batch_id: str, failed_files: List[str]) -> Dict[str, Any]:
    return _rt().batch_repair(batch_id, failed_files)


# ------------------------------------------------- memory / quality / ops
class MemoryBody(BaseModel):
    category: str
    trigger: str
    solution: str
    phase: str = ""
    versions: str = ""


class QualityBody(BaseModel):
    project_root: str
    build: bool = True
    typecheck: bool = True
    tests: bool = False
    browser: bool = False
    timeout: int = 300
    routes: List[str] = []
    background: bool = True


class GateBody(BaseModel):
    action: str
    reason: str = ""


@router.get("/runs/{run_id}/events")
def run_events(run_id: str, after: int = 0) -> Dict[str, Any]:
    try:
        return _rt().run_events(run_id, after=after)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/runs/{run_id}/gate")
def gate_run(run_id: str, body: GateBody) -> Dict[str, Any]:
    try:
        return _rt().gate_run(run_id, body.action, body.reason)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/runs/{run_id}/nodes/{node_id}/rerun")
def rerun_node(run_id: str, node_id: str) -> Dict[str, Any]:
    try:
        return _rt().rerun_node(run_id, node_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/agent-status")
def agents_status() -> Dict[str, Any]:
    rt = _rt()
    runs = rt.list_runs(limit=20)
    active: Dict[str, Any] = {}
    for run in runs:
        if run.get("status") not in ("running", "queued", "paused", "gated"):
            continue
        wf = rt.registry.get_workflow(run.get("workflow_id", ""))
        nodes = {n.get("id"): n for n in (wf.definition.get("nodes") if wf else []) or []}
        for node_id, gid in (run.get("batch_groups") or {}).items():
            node = nodes.get(node_id) or {}
            agent = node.get("agent") or ""
            st = rt.batch_status(gid)
            active.setdefault(agent, []).append({
                "run_id": run["id"], "node_id": node_id, "group_id": gid,
                "status": run.get("status"), "done": st["done_batches"],
                "total": st["total_batches"], "running": st["running"],
                "failed": st["failed"], "ready": st["ready"],
            })
    return {"agents": [{"id": a.id, "name": a.name, "active": active.get(a.id, [])}
                       for a in rt.registry.list_agents()]}


@router.get("/memory/experiences")
def list_experiences(query: str = "", phase: str = "", limit: int = 30) -> Dict[str, Any]:
    rows = _rt().experience_search(query=query, phase=phase, limit=max(1, min(limit, 100)))
    return {"experiences": rows, "count": len(rows)}


@router.post("/memory/experiences")
def add_experience(body: MemoryBody) -> Dict[str, Any]:
    try:
        return _rt().experience_add(category=body.category, trigger=body.trigger,
                                    solution=body.solution, phase=body.phase,
                                    versions=body.versions)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/quality")
def quality_evidence(limit: int = 20) -> Dict[str, Any]:
    rt = _rt()
    root = rt.data_dir / "quality"
    rows = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "name": path.name, "mtime": path.stat().st_mtime,
                "ok": data.get("ok"), "duration": data.get("duration"),
                "build": (data.get("build") or {}).get("ok") if isinstance(data.get("build"), dict) else None,
                "browser": (data.get("browser") or {}).get("ok") if isinstance(data.get("browser"), dict) else None,
                "browser_routes": len((data.get("browser") or {}).get("routes", []) or []),
                "gate": data.get("gate"),
                "evidence_path": str(path),
            })
        except Exception:  # noqa: BLE001
            continue
    return {"items": rows, "count": len(rows), "quality_dir": str(root)}


@router.post("/quality/collect")
def quality_collect(body: QualityBody) -> Dict[str, Any]:
    kwargs = dict(project_root=body.project_root, build=body.build,
                  typecheck=body.typecheck, tests=body.tests,
                  browser=body.browser, timeout=body.timeout,
                  routes=body.routes or None)
    if body.background:
        job = _QUALITY_JOBS.submit(_rt().quality_collect, kind="quality", **kwargs)
        return {"ok": True, "async": True, "job_id": job["id"], "status": job["status"]}
    try:
        return _rt().quality_collect(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/quality/jobs")
def quality_jobs(limit: int = 20) -> Dict[str, Any]:
    return {"ok": True, "jobs": _QUALITY_JOBS.list(limit=limit)}


@router.get("/quality/jobs/{job_id}")
def quality_job(job_id: str) -> Dict[str, Any]:
    job = _QUALITY_JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, f"quality job not found: {job_id}")
    return {"ok": True, **job}


@router.get("/audit")
def audit_evidence(limit: int = 20) -> Dict[str, Any]:
    rt = _rt()
    root = rt.data_dir / "audit"
    rows = []
    for path in sorted(root.rglob("violation-*.json"), key=lambda p: p.stat().st_mtime,
                       reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append({"name": path.name, "mtime": path.stat().st_mtime,
                         "violations": data.get("violations", []),
                         "restored": data.get("restored", []),
                         "removed": data.get("removed", []),
                         "evidence_path": str(path)})
        except Exception:  # noqa: BLE001
            continue
    return {"items": rows, "count": len(rows), "audit_dir": str(root)}


@router.get("/drivers")
def drivers() -> Dict[str, Any]:
    rt = _rt()
    lock_dir = rt.data_dir / "driver-locks"
    locks = []
    for path in sorted(lock_dir.glob("*.lock"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
        locks.append({"group_id": path.stem, "pid": data.get("pid"),
                      "age": round(time.time() - path.stat().st_mtime, 1),
                      "lock_path": str(path)})
    return {"locks": locks, "count": len(locks)}


@router.get("/settings")
def settings() -> Dict[str, Any]:
    rt = _rt()
    return {
        "version": "0.2.0", "data_dir": str(rt.data_dir), "plugin_root": str(rt.plugin_root),
        "backend": rt.backend, "backend_info": rt.backend_info(),
        "counts": {"agents": len(rt.registry.list_agents()),
                   "skills": len(rt.registry.list_skills()),
                   "workflows": len(rt.registry.list_workflows()),
                   "runs": len(rt.list_runs(limit=100))},
        "thresholds": {"pass": 85, "warn": 70, "max_rework": 3,
                       "max_files_per_batch": 7, "context_budget_chars": 28000},
        "driver": {"default_max_seconds": 240, "hard_cap_seconds": 360,
                   "audit_default": True, "max_concurrent_batches": 1},
        "registry_errors": rt.registry.last_errors,
    }
