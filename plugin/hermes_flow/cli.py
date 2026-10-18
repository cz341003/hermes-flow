"""``hermes flow`` CLI：状态、注册中心、工作流、批次演示。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .flow_core.batch import BatchPolicy, FileItem, plan_batches
from .flow_core.engine.scheduler import ExecutionResult
from .flow_core.orchestrator import WorkflowOrchestrator
from .runtime import FlowRuntime, get_runtime


def setup(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", choices=["sqlite", "loopx"], default=None,
                        help="State kernel backend (default: config/env, else sqlite)")
    subs = parser.add_subparsers(dest="flow_command")
    subs.add_parser("status", help="Print runtime/registry status as JSON")
    subs.add_parser("doctor", help="Check backend/kernel/LoopX availability and fallback")
    p = subs.add_parser("backend", help="Show or set the state kernel backend")
    p.add_argument("--set", choices=["sqlite", "loopx"], default=None)
    subs.add_parser("agents", help="List registered experts")
    subs.add_parser("skills", help="List skills")
    subs.add_parser("workflows", help="List workflow templates")
    p = subs.add_parser("demo", help="Run a deterministic 6-phase batch demo (no LLM)")
    p.add_argument("--files", type=int, default=287, help="Synthetic file count (default 287)")
    p.add_argument("--batch-size", type=int, default=7)
    p = subs.add_parser("plan-batch", help="Plan batches from a files JSON")
    p.add_argument("files", help="JSON file: [{path,size,deps,risk}]")
    p.add_argument("--batch-size", type=int, default=7)
    p = subs.add_parser("board", help="Render HTML board")
    p.add_argument("--out", default="")
    p = subs.add_parser("run", help="Run a workflow with a deterministic mock runner")
    p.add_argument("workflow_id")
    p.add_argument("--files", type=int, default=20)
    p.add_argument("--project-root", default="")
    p.add_argument("--out", default="")
    p = subs.add_parser("verify", help="Run real build/typecheck on a project (quality collector)")
    p.add_argument("project_root")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--browser", action="store_true")


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def run(args: argparse.Namespace) -> int:
    rt = get_runtime()
    backend = getattr(args, "backend", None)
    if backend and backend != rt.backend:
        rt = FlowRuntime(rt.plugin_root, rt.data_dir, backend=backend)
    cmd = getattr(args, "flow_command", None)
    if cmd == "doctor":
        info = rt.backend_info()
        _print(info)
        return 0 if info.get("kernel_ok") and not info.get("error") else 1
    if cmd == "backend":
        if getattr(args, "set", None):
            _print(rt.set_backend(args.set))
        else:
            _print(rt.backend_info())
        return 0
    if cmd == "status":
        _print(rt.status())
        return 0
    if cmd == "agents":
        _print([a.to_dict() for a in rt.registry.list_agents()])
        return 0
    if cmd == "skills":
        _print([s.to_dict() for s in rt.registry.list_skills()])
        return 0
    if cmd == "workflows":
        _print([{k: v for k, v in w.to_dict().items() if k != "definition"}
                for w in rt.registry.list_workflows()])
        return 0
    if cmd == "board":
        html = rt.render_board(out=args.out)
        _print({"ok": True, "path": args.out, "size": len(html)})
        return 0
    if cmd == "verify":
        out = rt.quality_collect(project_root=args.project_root, browser=args.browser,
                                 timeout=args.timeout)
        _print(out)
        return 0 if out.get("ok") else 1
    if cmd == "plan-batch":
        try:
            raw = json.loads(Path(args.files).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"读取文件清单失败: {exc}", file=sys.stderr)
            return 2
        items = [FileItem.from_dict(x) for x in raw]
        plan = plan_batches(items, BatchPolicy(max_files_per_batch=args.batch_size))
        _print(plan.to_dict())
        return 0
    if cmd in ("demo", "run"):
        workflow_id = args.workflow_id if cmd == "run" else "vue3-migrate-6phase"
        wf = rt.registry.get_workflow(workflow_id)
        if wf is None:
            print(f"工作流不存在: {workflow_id}", file=sys.stderr)
            return 2
        n_files = args.files
        files = _synthetic_files(n_files, project_root=getattr(args, "project_root", ""))
        files_by_node = _files_for_batch_nodes(wf.definition, files)
        runner = _make_mock_runner()
        orch = WorkflowOrchestrator(rt.queue)
        result = orch.run(wf.definition, runner, run_id=f"cli-{cmd}",
                          project_root=getattr(args, "project_root", ""),
                          files_by_node=files_by_node)
        _print(result.to_dict())
        if getattr(args, "out", ""):
            Path(args.out).write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if result.done else 1
    print("用法: hermes flow [--backend sqlite|loopx] "
          "{status|doctor|backend|agents|skills|workflows|demo|plan-batch|run|verify|board}")
    return 2


def _synthetic_files(n: int, project_root: str = "") -> List[Dict[str, Any]]:
    files = []
    for i in range(n):
        rel = f"src/components/C{i:03d}.vue"
        files.append({
            "path": rel,
            "size": 1800,
            "deps": [f"src/components/C{i-1:03d}.vue"] if i % 7 else [],
            "risk": "high" if i % 23 == 0 else "low",
        })
    return files


def _files_for_batch_nodes(definition: Dict[str, Any], files: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out = {}
    for node in definition.get("nodes", []):
        if node.get("type") == "batch":
            out[node["id"]] = files
    return out


def _make_mock_runner():
    """确定性替身：正常批次直接成功；超大批次模拟截断以验证 split。"""
    import time

    def runner(node, ctx):
        files = ctx.get("files") or []
        if len(files) > 12:
            return ExecutionResult(success=False, truncated=True, error="mock truncation")
        time.sleep(0.001)
        return ExecutionResult(success=True, score=90, artifacts=[f["path"] for f in files])
    return runner
