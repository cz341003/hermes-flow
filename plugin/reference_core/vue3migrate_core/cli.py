"""vue3migrate-core 命令行入口：``python -m vue3migrate_core <command>``。

这是内核的统一 CLI，同时服务两种形态：
- Hermes 插件（可选直接复用）；
- dsh 插件（Node 侧通过 child_process 调用本 CLI 驱动 Python 内核）。

支持 ``--backend sqlite|loopx`` 切换内核后端，输出 JSON 便于程序化解析。
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

from .adapters import create_kernel
from .engine import Scheduler, Workflow


def _out(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _kernel(args) -> Any:
    if args.backend == "sqlite":
        return create_kernel("sqlite", db_path=args.db)
    return create_kernel("loopx", root=args.root)


# ---------------------------------------------------------------------------
# 子命令 handlers
# ---------------------------------------------------------------------------
def cmd_goal_create(args) -> None:
    k = _kernel(args)
    try:
        g = k.create_goal(args.title, args.description or "",
                          quota_total=args.quota)
        _out({"ok": True, "goal_id": g.id, "status": g.status})
    finally:
        k.close()


def cmd_goal_should_run(args) -> None:
    k = _kernel(args)
    try:
        r = k.should_run(args.goal_id)
        _out({"ok": True, "should": r.should, "reason": r.reason})
    finally:
        k.close()


def cmd_todo_create(args) -> None:
    k = _kernel(args)
    try:
        t = k.create_todo(args.goal_id, args.file, args.phase,
                          dependencies=args.dep or None)
        _out({"ok": True, "todo_id": t.id, "status": t.status})
    finally:
        k.close()


def cmd_todo_claim(args) -> None:
    k = _kernel(args)
    try:
        t = k.claim(args.goal_id, args.agent or "cli-agent")
        if t is None:
            _out({"ok": False, "reason": "无可认领切片（依赖未满足或已终态）"})
        else:
            _out({"ok": True, "todo_id": t.id, "file": t.file_path,
                  "phase": t.phase, "status": t.status})
    finally:
        k.close()


def cmd_todo_update(args) -> None:
    k = _kernel(args)
    try:
        t = k.update(args.todo_id, args.status)
        _out({"ok": True, "todo_id": t.id, "status": t.status,
              "attempts": t.attempts})
    finally:
        k.close()


def cmd_state_refresh(args) -> None:
    k = _kernel(args)
    try:
        snap = k.refresh_state(args.goal_id)
        nxt = snap.next_todo
        _out({"ok": True, "progress": snap.progress,
              "next_todo": nxt.id if nxt else None,
              "goal_status": snap.goal.status if snap.goal else None,
              "related_experiences": len(snap.related_experiences)})
    finally:
        k.close()


def cmd_quota_spend(args) -> None:
    k = _kernel(args)
    try:
        ok = k.spend_slot(args.goal_id, args.n)
        _out({"ok": ok})
    finally:
        k.close()


def _build_demo() -> Workflow:
    from .engine import Edge, Node
    wf = Workflow(id="demo", name="Vue2→Vue3 迁移模板")
    wf.nodes = [
        Node("analyze", "结构分析", "analyze", agent="结构分析专家", skill="vue3-analyze"),
        Node("deps", "依赖分析", "deps", agent="依赖分析专家", skill="vue3-deps"),
        Node("transform", "代码转化", "transform", agent="代码转化专家", skill="vue3-transform"),
        Node("quality", "质量分析", "quality", agent="质量分析专家", skill="vue3-quality"),
        Node("verify", "浏览器验证", "verify", agent="浏览器验证专家", skill="vue3-verify"),
        Node("fix", "修复回环", "fix", agent="修复专家", skill="vue3-fix"),
    ]
    wf.edges = [
        Edge("analyze", "deps"), Edge("deps", "transform"),
        Edge("transform", "quality"), Edge("quality", "verify"),
        Edge("quality", "fix"),
    ]
    return wf


def cmd_workflow_demo(args) -> None:
    from .engine import ExecutionResult
    wf = _build_demo()
    sched = Scheduler(wf)
    trace = []

    def runner(node, ctx):
        trace.append(node.id)
        return ExecutionResult(success=True)  # 占位：真实执行由 agent 委派完成

    report = sched.run(runner)
    _out({"ok": True, "done": report.done, "topo_order": trace,
          "states": sched.states()})


def cmd_workflow_run(args) -> None:
    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)
    from .engine import Edge, ExecutionResult, Node
    wf = Workflow(id=data.get("id", "wf"), name=data.get("name", "workflow"))
    wf.nodes = [Node(**n) for n in data["nodes"]]
    wf.edges = [Edge(**e) for e in data.get("edges", [])]
    sched = Scheduler(wf)
    trace = []

    def runner(node, ctx):
        trace.append(node.id)
        return ExecutionResult(success=True)

    report = sched.run(runner)
    _out({"ok": True, "done": report.done, "topo_order": trace,
          "states": sched.states()})


# ---------------------------------------------------------------------------
# argparse 构建
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vue3migrate-core",
                                description="Vue2→Vue3 迁移内核 CLI")
    p.add_argument("--backend", choices=["sqlite", "loopx"], default="sqlite")
    p.add_argument("--db", default=":memory:")
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("goal-create")
    g.add_argument("--title", required=True)
    g.add_argument("--description")
    g.add_argument("--quota", type=int, default=0)
    g.set_defaults(func=cmd_goal_create)

    g = sub.add_parser("goal-should-run")
    g.add_argument("--goal-id", required=True)
    g.set_defaults(func=cmd_goal_should_run)

    g = sub.add_parser("todo-create")
    g.add_argument("--goal-id", required=True)
    g.add_argument("--file", required=True)
    g.add_argument("--phase", required=True)
    g.add_argument("--dep", action="append")
    g.set_defaults(func=cmd_todo_create)

    g = sub.add_parser("todo-claim")
    g.add_argument("--goal-id", required=True)
    g.add_argument("--agent")
    g.set_defaults(func=cmd_todo_claim)

    g = sub.add_parser("todo-update")
    g.add_argument("--todo-id", required=True)
    g.add_argument("--status", choices=["done", "failed", "blocked"], required=True)
    g.set_defaults(func=cmd_todo_update)

    g = sub.add_parser("state-refresh")
    g.add_argument("--goal-id", required=True)
    g.set_defaults(func=cmd_state_refresh)

    g = sub.add_parser("quota-spend")
    g.add_argument("--goal-id", required=True)
    g.add_argument("--n", type=int, default=1)
    g.set_defaults(func=cmd_quota_spend)

    g = sub.add_parser("workflow-demo")
    g.set_defaults(func=cmd_workflow_demo)

    g = sub.add_parser("workflow-run")
    g.add_argument("--file", required=True)
    g.set_defaults(func=cmd_workflow_run)

    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI 顶层兜底
        _out({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
