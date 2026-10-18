"""HERMES Flow — 多智能体迁移控制面（Hermes 插件入口）。

``register(ctx)`` 完成：
1. 初始化运行时（plugin_root / plugin-data 数据目录）
2. 注册 30+ ``flow_*`` 工具
3. 注册 ``hermes flow`` CLI
4. 注册 ``pre_llm_call`` 钩子（注入活跃 Run / 经验，失败静默）
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from . import cli, tools
from .runtime import configure, get_runtime

PLUGIN_ROOT = Path(__file__).resolve().parent
__version__ = "0.3.0"


def _resolve_data_dir(ctx: Any) -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir  # type: ignore
        return Path(plugin_data_dir("hermes_flow"))
    except Exception:  # noqa: BLE001 - 独立运行时降级
        home = os.environ.get("HERMES_HOME") or r"E:\hermes"
        return Path(home) / "plugin-data" / "hermes_flow"


def _pre_llm_call(**kwargs: Any) -> Any:
    """每轮注入：活跃 Run 的批次进度 + 与当前用户消息相关的迁移经验（≤9k 字符）。"""
    try:
        rt = get_runtime()
        bits = []
        runs = [r for r in rt.list_runs(limit=5) if r.get("status") in ("running", "queued", "paused", "gated")]
        if runs:
            run = runs[0]
            bits.append(f"[HERMES Flow] 活跃 Run {run['id']}（{run.get('workflow_name', '')}）")
            for node, gid in (run.get("batch_groups") or {}).items():
                st = rt.batch_status(gid)
                bits.append(f"- {node}: 批次 {st['done_batches']}/{st['total_batches']}，"
                            f"运行中 {len(st['running'])}，失败 {len(st['failed'])}")
            if run.get("status") == "gated":
                bits.append("- 当前 Run 处于 gated（写入边界/人工门），批准或驳回后再继续。")
        # 以当前用户消息为 query 召回经验；没有消息时给最近经验兜底。
        message = kwargs.get("user_message") or ""
        if isinstance(message, list):
            message = " ".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in message)
        query = str(message).strip()[:300]
        experiences = rt.experience_search(query=query, limit=3)
        if experiences:
            bits.append("[HERMES Flow] 相关迁移经验（来自经验库，按相关性排序）：")
            for e in experiences:
                trigger = str(e.get("trigger", ""))[:120]
                solution = str(e.get("solution", ""))[:400]
                bits.append(f"- {e.get('category', '')} · {trigger} → {solution}")
        if not bits:
            return None
        return {"context": "\n".join(bits)[:9000]}
    except Exception:  # noqa: BLE001 - 钩子永不阻塞主流程
        return None


def _slash_flow(raw_args: str = "") -> str:
    """``/flow`` in-session slash command: status/agents/skills/workflows/batches/help."""
    try:
        rt = get_runtime()
        argv = (raw_args or "").strip().split()
        sub = argv[0].lower() if argv else "status"
        if sub in ("help", "-h", "--help"):
            return (
                "**HERMES Flow**\n"
                "- `/flow status` — 当前 Run 与批次进度\n"
                "- `/flow agents` — 已加载专家\n"
                "- `/flow skills` — 已加载技能\n"
                "- `/flow workflows` — 工作流模板\n"
                "- `/flow batches` — 活跃批次队列\n"
                "Dashboard 页签：左侧 **HERMES Flow**（路径 `/flow`）"
            )
        if sub == "agents":
            agents = rt.registry.list_agents()
            lines = [f"- **{a.name}** (`{a.id}`) · 技能 {', '.join(a.skills) or '无'}" for a in agents]
            return "**已加载专家（%d）**\n%s" % (len(agents), "\n".join(lines) or "（空）")
        if sub == "skills":
            skills = rt.registry.list_skills()
            lines = [f"- **{s.name}** (`{s.id}`) · phases: {', '.join(s.phases) or '-'}" for s in skills]
            return "**已加载技能（%d）**\n%s" % (len(skills), "\n".join(lines) or "（空）")
        if sub == "workflows":
            wfs = rt.registry.list_workflows()
            lines = [f"- **{w.name}** (`{w.id}`) · v{w.version}" for w in wfs]
            return "**工作流模板（%d）**\n%s" % (len(wfs), "\n".join(lines) or "（空）")
        runs = rt.list_runs(limit=5)
        active = [r for r in runs if r.get("status") in ("running", "queued", "paused")]
        if sub == "batches":
            if not active:
                return "当前没有活跃 Run。用 `/flow status` 查看历史，或在 Dashboard 创建 Run。"
            parts = []
            for run in active:
                parts.append(f"**Run `{run['id']}`** · {run.get('workflow_name', '')} · {run.get('status')}")
                for node, gid in (run.get("batch_groups") or {}).items():
                    st = rt.batch_status(gid)
                    parts.append(f"- {node}: 批次 {st['done_batches']}/{st['total_batches']}，"
                                 f"运行中 {len(st['running'])}，失败 {len(st['failed'])}")
            return "\n".join(parts)
        # status（默认）
        parts = [f"**HERMES Flow** · {len(rt.registry.list_agents())} 专家 / "
                 f"{len(rt.registry.list_skills())} 技能 / {len(rt.registry.list_workflows())} 工作流"]
        if not active:
            parts.append("当前没有活跃 Run；到 Dashboard 的 **HERMES Flow** 页签创建工作流。")
        for run in active[:3]:
            parts.append(f"- Run `{run['id']}` · {run.get('workflow_name', '')} · {run.get('status')}")
            for node, gid in (run.get("batch_groups") or {}).items():
                st = rt.batch_status(gid)
                parts.append(f"  - {node}: 批次 {st['done_batches']}/{st['total_batches']}"
                             f"（运行 {len(st['running'])} / 失败 {len(st['failed'])}）")
        return "\n".join(parts)
    except Exception as exc:  # noqa: BLE001 - slash command 不应让会话崩溃
        return f"HERMES Flow 暂时不可用：{exc}"


def register(ctx: Any) -> None:
    rt = configure(plugin_root=PLUGIN_ROOT, data_dir=_resolve_data_dir(ctx),
                   backend=os.environ.get("HERMES_FLOW_BACKEND"))
    if hasattr(ctx, "subagent_lifecycle"):
        rt.set_lifecycle(ctx.subagent_lifecycle)
    tools.register_tools(ctx)
    ctx.register_cli_command(
        name="flow", help="HERMES Flow migration control plane (status/agents/workflows/demo)",
        setup_fn=cli.setup, handler_fn=cli.run,
        description="Inspect and drive the HERMES Flow migration control plane.",
    )
    try:
        ctx.register_command(
            "flow", handler=_slash_flow,
            description="HERMES Flow: status/agents/skills/workflows/batches/help",
            args_hint="[status|agents|skills|workflows|batches|help]",
        )
    except Exception:  # noqa: BLE001 - 旧版本无 register_command 时降级
        pass
    try:
        ctx.register_hook("pre_llm_call", _pre_llm_call)
    except Exception:  # noqa: BLE001 - 旧版本无该 hook 时降级
        pass
