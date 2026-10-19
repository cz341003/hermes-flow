import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("HERMES_FLOW_PLUGIN_ROOT", r"E:\deepSeek\plugin\hermes_flow"))
DATA = Path(os.environ.get("HERMES_FLOW_DATA_DIR")
            or (Path.home() / ".dsh" / "plugin-data" / "hermes_flow"))
sys.path.insert(0, str(ROOT.parent))

from hermes_flow.runtime import FlowRuntime  # noqa: E402

rt = FlowRuntime(ROOT, DATA)
EXCLUDE = {"node_modules", "dist", "coverage", ".git", ".vite", "build"}
EXTS = {".vue", ".js", ".ts", ".jsx", ".tsx", ".less", ".scss", ".css", ".json"}


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
