import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(os.environ.get("HERMES_FLOW_PLUGIN_ROOT", r"E:\deepSeek\plugin\hermes_flow"))
DATA = Path(os.environ.get("HERMES_FLOW_DATA_DIR")
            or (Path.home() / ".dsh" / "plugin-data" / "hermes_flow"))
sys.path.insert(0, str(ROOT.parent))

from hermes_flow.runtime import FlowRuntime  # noqa: E402
from hermes_flow.flow_core.batch.driver import BatchAutoDriver  # noqa: E402

rt = FlowRuntime(ROOT, DATA)
EXCLUDE = {"node_modules", "dist", "coverage", ".git", ".vite", "build"}
EXTS = {".vue", ".js", ".ts", ".jsx", ".tsx", ".less", ".scss", ".css", ".json"}


class DshLauncher:
    """把 driver 的 launch/wait/result 通过 stdio 反向委托给 Node/DSH subagent。"""
    def __init__(self):
        self._seq = 0
        self._handle = {}
        self._lock = threading.Lock()

    def launch(self, *, goal, context, metadata, correlation_id):
        with self._lock:
            self._seq += 1
            rid = f"launch-{self._seq}"
            req = {"id": rid, "method": "__launch__", "params": {
                "goal": goal, "context": context, "metadata": metadata,
                "correlation_id": correlation_id,
            }}
            sys.stdout.write(json.dumps(req, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            while True:
                line = sys.stdin.readline()
                if not line:
                    raise RuntimeError("DSH launcher: sidecar stdin closed")
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if str(msg.get("id")) != rid:
                    # 非本请求的响应：当前协议只允许单并发 batch_auto
                    continue
                if not msg.get("ok"):
                    raise RuntimeError(msg.get("error") or "DSH subagent launch failed")
                result = msg.get("result") or {}
                handle = {"_rid": rid, "_summary": result.get("summary"),
                          "_state": result.get("terminal_state") or "SUCCEEDED",
                          "child_id": result.get("child_id", "")}
                self._handle[rid] = handle
                return handle

    def wait(self, handle, *, timeout):
        return {"completed": True, "timed_out": False, "state": "SUCCEEDED"}

    def result(self, handle):
        return {"terminal_state": handle.get("_state") or "SUCCEEDED",
                "summary": handle.get("_summary"),
                "error_message": handle.get("error_message") or "",
                "error_classification": ""}

    def cancel(self, handle, *, reason):
        return False


def _find_run_for_group(group_id: str):
    for run in rt.list_runs(limit=500):
        if group_id in (run.get("batch_groups") or {}).values():
            return run
    return None


def batch_auto(params: dict):
    group_id = str(params["group_id"])
    run = _find_run_for_group(group_id)
    project_root = str(params.get("project_root") or (run or {}).get("project_root") or "")
    driver = BatchAutoDriver(
        rt.queue, DshLauncher(),
        staging_base=rt.data_dir / "staging",
        project_root=project_root,
        lock_dir=rt.data_dir / "driver-locks",
        audit=bool(params.get("audit", True)),
        audit_dir=rt.data_dir / "audit",
        concurrency=int(params["concurrency"]) if params.get("concurrency") else None,
        worktree_base=rt.data_dir / "worktrees",
    )
    return driver.drive(
        group_id,
        max_batches=int(params.get("max_batches", 1) or 1),
        max_seconds=float(params.get("max_seconds", 240) or 240),
        apply=bool(params.get("apply", True)),
    ).to_dict()


def scan_project(root: str):
    base = Path(root).resolve()
    if not base.is_dir():
        raise ValueError(f"project_root 不是目录: {root}")
    out = []
    for p in base.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        if any(part in EXCLUDE for part in p.parts):
            continue
        out.append({"path": p.relative_to(base).as_posix(), "size": p.stat().st_size})
    return {"project_root": str(base), "count": len(out), "files": out}


def dispatch(method: str, params: dict):
    if method == "status":
        return rt.status()
    if method == "agents":
        return {"agents": [a.to_dict() for a in rt.registry.list_agents()]}
    if method == "skills":
        return {"skills": [s.to_dict() for s in rt.registry.list_skills()]}
    if method == "workflows":
        return {"workflows": [{k: v for k, v in w.to_dict().items() if k != "definition"}
                              for w in rt.registry.list_workflows()]}
    if method == "scan_project":
        return scan_project(str(params.get("project_root", "")))
    if method == "run_start":
        files = params.get("files") or []
        if not files and params.get("project_root"):
            files = scan_project(str(params["project_root"]))["files"]
        return rt.start_run(workflow_id=str(params["workflow_id"]),
                            project_root=str(params.get("project_root", "")),
                            files=files, title=str(params.get("title", "")))
    if method == "batch_plan":
        return rt.batch_plan(run_id=str(params["run_id"]), node_id=str(params["node_id"]),
                             files=params.get("files") or None,
                             policy=params.get("policy") or None)
    if method == "batch_status":
        return rt.batch_status(str(params["group_id"]))
    if method == "batch_auto":
        return batch_auto(params)
    if method == "batch_items":
        return rt.batch_items(str(params["batch_id"]))
    if method == "quality_collect":
        return rt.quality_collect(project_root=str(params["project_root"]),
                                  browser=bool(params.get("browser", False)),
                                  timeout=int(params.get("timeout", 300)))
    if method == "quality_gate":
        return rt.quality_gate(project_root=str(params["project_root"]),
                               batch_scores=list(params.get("batch_scores") or []),
                               coverage=float(params.get("coverage", 1.0)),
                               browser=bool(params.get("browser", False)),
                               timeout=int(params.get("timeout", 300)))
    if method == "backend":
        return rt.backend_info()
    if method == "set_backend":
        return rt.set_backend(str(params["backend"]))
    if method == "experience_search":
        return {"experiences": rt.experience_search(query=str(params.get("query", "")),
                                                    limit=int(params.get("limit", 5)))}
    if method == "experience_add":
        return rt.experience_add(category=str(params["category"]),
                                 trigger=str(params["trigger"]),
                                 solution=str(params["solution"]),
                                 versions=str(params.get("versions", "")))
    if method == "audit":
        root = rt.data_dir / "audit"
        items = []
        if root.is_dir():
            for p in sorted(root.rglob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                try:
                    items.append({"name": p.name, "path": str(p), "data": json.loads(p.read_text(encoding="utf-8"))})
                except Exception:
                    pass
        return {"items": items}
    if method == "shutdown":
        raise SystemExit(0)
    raise ValueError(f"未知方法: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            result = dispatch(str(req.get("method", "")), req.get("params") or {})
            resp = {"id": req.get("id"), "ok": True, "result": result}
        except SystemExit:
            return 0
        except Exception as exc:  # noqa: BLE001
            resp = {"id": None, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
