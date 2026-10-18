"""HERMES Flow 工具层：注册到 Hermes 的 24+ 个 ``flow_*`` 工具。

每个 handler 签名 ``(args: dict, **_kw) -> str``，返回 JSON 字符串。
工具只做参数校验与状态读写，耗时执行由 agent turn / 子代理完成。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from .runtime import FlowRuntime, get_runtime
from .flow_core.recovery import classify

TOOLSET = "hermes_flow"


def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False)


def _err(message: str, code: str = "FLOW_INTERNAL") -> str:
    return json.dumps({"ok": False, "error": message, "code": code}, ensure_ascii=False)


def _schema(name: str, description: str, properties: Dict[str, Any],
            required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


def _json_arg(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _rt() -> FlowRuntime:
    return get_runtime()


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
AGENT_CREATE = _schema(
    "flow_agent_create",
    "Create a migration expert (agent) from a role prompt; bind 0..N skills and optional loop policy.",
    {
        "name": {"type": "string", "description": "专家名称，如“代码转化专家”"},
        "role": {"type": "string", "description": "角色提示词，≥20 字符"},
        "description": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}, "description": "技能 id 列表"},
        "model": {"type": "string"},
        "toolsets": {"type": "array", "items": {"type": "string"}},
        "loop_policy": {"type": "object", "description": "批次循环配置（FR-10）"},
    },
    required=["name", "role"],
)


def handle_agent_create(args: Dict[str, Any], **_kw) -> str:
    try:
        spec = _rt().registry.create_agent(args)
        return _ok(spec.to_dict())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_AGENT_INVALID")


def handle_agent_list(args: Dict[str, Any], **_kw) -> str:
    agents = [a.to_dict() for a in _rt().registry.list_agents()]
    return _ok({"agents": agents, "count": len(agents)})


def handle_agent_get(args: Dict[str, Any], **_kw) -> str:
    spec = _rt().registry.get_agent(str(args.get("agent_id", "")))
    if spec is None:
        return _err(f"专家不存在: {args.get('agent_id')}", "FLOW_NOT_FOUND")
    return _ok(spec.to_dict())


def handle_agent_update(args: Dict[str, Any], **_kw) -> str:
    try:
        patch = dict(args)
        agent_id = str(patch.pop("agent_id", ""))
        spec = _rt().registry.update_agent(agent_id, patch)
        return _ok(spec.to_dict())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_AGENT_INVALID")


def handle_agent_delete(args: Dict[str, Any], **_kw) -> str:
    try:
        ok = _rt().registry.delete_agent(str(args.get("agent_id", "")))
        return _ok({"deleted": ok})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_AGENT_DELETE")


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
SKILL_CREATE = _schema(
    "flow_skill_create",
    "Create a standard SKILL.md skill (validates frontmatter and sections).",
    {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "body": {"type": "string", "description": "正文（含 Procedure/Pitfalls/Verification）"},
        "phases": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    required=["name", "description", "body"],
)


def handle_skill_create(args: Dict[str, Any], **_kw) -> str:
    try:
        spec = _rt().registry.create_skill(
            str(args.get("name")), str(args.get("description")),
            str(args.get("body")), phases=args.get("phases") or [],
            tags=args.get("tags") or [])
        return _ok(spec.to_dict())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_SKILL_INVALID")


def handle_skill_list(args: Dict[str, Any], **_kw) -> str:
    skills = [s.to_dict() for s in _rt().registry.list_skills()]
    return _ok({"skills": skills, "count": len(skills)})


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------
WORKFLOW_CREATE = _schema(
    "flow_workflow_create",
    "Create/validate a workflow DAG (JSON string). Batch nodes support FR-10 config.",
    {"definition": {"type": "string", "description": "JSON string of workflow"}},
    required=["definition"],
)


def handle_workflow_create(args: Dict[str, Any], **_kw) -> str:
    try:
        data = _json_arg(args.get("definition"), {})
        tmpl = _rt().registry.save_workflow(data)
        return _ok(tmpl.to_dict())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_WORKFLOW_INVALID")


def handle_workflow_list(args: Dict[str, Any], **_kw) -> str:
    items = [{k: v for k, v in w.to_dict().items() if k != "definition"}
             for w in _rt().registry.list_workflows()]
    return _ok({"workflows": items, "count": len(items)})


def handle_workflow_get(args: Dict[str, Any], **_kw) -> str:
    w = _rt().registry.get_workflow(str(args.get("workflow_id", "")))
    if w is None:
        return _err("工作流不存在", "FLOW_NOT_FOUND")
    return _ok(w.to_dict())


def handle_workflow_validate(args: Dict[str, Any], **_kw) -> str:
    data = _json_arg(args.get("definition"), {})
    ok, errors = _rt().registry.validate_workflow(data)
    return _ok({"valid": ok, "errors": errors})


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
RUN_START = _schema(
    "flow_run_start",
    "Create a Run for a workflow (does not execute by itself; drive via flow_batch_next).",
    {
        "workflow_id": {"type": "string"},
        "project_root": {"type": "string"},
        "files": {"type": "array", "items": {"type": "object"}},
        "title": {"type": "string"},
    },
    required=["workflow_id"],
)


def handle_run_start(args: Dict[str, Any], **_kw) -> str:
    try:
        run = _rt().start_run(
            workflow_id=str(args.get("workflow_id")),
            project_root=str(args.get("project_root", "")),
            files=_json_arg(args.get("files"), []),
            title=str(args.get("title", "")),
        )
        return _ok(run)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_RUN_START")


def handle_run_status(args: Dict[str, Any], **_kw) -> str:
    run_id = str(args.get("run_id", ""))
    if run_id:
        run = _rt().get_run(run_id)
        if run is None:
            return _err("Run 不存在", "FLOW_NOT_FOUND")
        return _ok(run)
    return _ok({"runs": _rt().list_runs()})


def _set_run_status(run_id: str, status: str) -> str:
    run = _rt().update_run_status(run_id, status)
    if run is None:
        return _err("Run 不存在", "FLOW_NOT_FOUND")
    return _ok({"run_id": run_id, "status": status})


def handle_run_pause(args: Dict[str, Any], **_kw) -> str:
    return _set_run_status(str(args.get("run_id", "")), "paused")


def handle_run_resume(args: Dict[str, Any], **_kw) -> str:
    return _set_run_status(str(args.get("run_id", "")), "running")


def handle_run_cancel(args: Dict[str, Any], **_kw) -> str:
    return _set_run_status(str(args.get("run_id", "")), "cancelled")


# ---------------------------------------------------------------------------
# Batches (FR-10)
# ---------------------------------------------------------------------------
BATCH_PLAN = _schema(
    "flow_batch_plan",
    "Plan topological waves + budget-packed batches for a batch node; persists a batch group.",
    {
        "run_id": {"type": "string"},
        "node_id": {"type": "string"},
        "files": {"type": "array", "items": {"type": "object"}},
        "policy": {"type": "object"},
    },
    required=["run_id", "node_id"],
)


def handle_batch_plan(args: Dict[str, Any], **_kw) -> str:
    try:
        out = _rt().batch_plan(
            run_id=str(args.get("run_id")), node_id=str(args.get("node_id")),
            files=_json_arg(args.get("files"), None),
            policy=_json_arg(args.get("policy"), None))
        return _ok(out)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_BATCH_PLAN")


BATCH_NEXT = _schema(
    "flow_batch_next",
    "Claim the next ready batch and return a Batch Packet (absolute paths, staging, contract).",
    {"group_id": {"type": "string"}, "owner": {"type": "string"}},
    required=["group_id"],
)


def handle_batch_next(args: Dict[str, Any], **_kw) -> str:
    try:
        return _ok(_rt().batch_next(group_id=str(args.get("group_id")),
                                    owner=str(args.get("owner", "agent"))))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_BATCH_NEXT")


BATCH_STATUS = _schema(
    "flow_batch_status",
    "Report batch queue state (batches, items, running/ready/failed).",
    {"group_id": {"type": "string"}}, required=["group_id"],
)


def handle_batch_status(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().batch_status(str(args.get("group_id", ""))))


BATCH_ITEMS = _schema(
    "flow_batch_items",
    "List per-file items of a batch.",
    {"batch_id": {"type": "string"}}, required=["batch_id"],
)


def handle_batch_items(args: Dict[str, Any], **_kw) -> str:
    return _ok({"batch_id": args.get("batch_id"),
                "items": _rt().batch_items(str(args.get("batch_id", "")))})


BATCH_AUTO = _schema(
    "flow_batch_auto",
    "自动驱动批次组：认领→启动子代理→等待/校验→ingest/apply→质量门→下一批。"
    "必须在 Hermes agent turn 内调用（依赖 ctx.subagent_lifecycle）。",
    {
        "group_id": {"type": "string", "description": "batch_plan 返回的 group_id"},
        "max_batches": {"type": "integer", "description": "本次最多推进批次数，默认 1"},
        "max_seconds": {"type": "number", "description": "本次时间预算（秒），默认 240；必须小于 Hermes 工具 420s 上限，driver 硬上限 360"},
        "apply": {"type": "boolean", "description": "是否把 staging 应用到工作区，默认 true"},
        "audit": {"type": "boolean", "description": "运行后审计越界写并回滚，默认 true"},
        "concurrency": {"type": "integer", "description": "同 wave 并行批次数（1–3），默认取组策略"},
        "quality": {"type": "boolean", "description": "批次全部完成后自动跑 build/typecheck/browser + 聚合门，默认 false"},
        "browser": {"type": "boolean", "description": "quality=true 时是否做 Chrome 路由验证，默认 false"},
        "owner": {"type": "string", "description": "driver 所有者标识（单例锁）"},
    },
    required=["group_id"],
)


def handle_batch_auto(args: Dict[str, Any], **_kw) -> str:
    try:
        concurrency = args.get("concurrency")
        out = _rt().auto_drive(
            group_id=str(args.get("group_id")),
            max_batches=int(args.get("max_batches", 1) or 1),
            max_seconds=float(args.get("max_seconds", 240) or 240),
            apply=bool(args.get("apply", True)),
            audit=bool(args.get("audit", True)),
            concurrency=(int(concurrency) if concurrency else None),
            quality=bool(args.get("quality", False)),
            browser=bool(args.get("browser", False)),
            owner=str(args.get("owner", "hermes-flow-driver")),
        )
        return _ok(out)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_DRIVER_ERROR")


BATCH_INGEST = _schema(
    "flow_batch_ingest",
    "Ingest per-file results from a subagent; optionally verify staging and apply to workspace.",
    {
        "group_id": {"type": "string"},
        "batch_id": {"type": "string"},
        "results": {"type": "array", "items": {"type": "object"}},
        "attempt_id": {"type": "string"},
        "staging_root": {"type": "string"},
        "project_root": {"type": "string"},
        "apply": {"type": "boolean"},
    },
    required=["group_id", "batch_id", "results"],
)


def handle_batch_ingest(args: Dict[str, Any], **_kw) -> str:
    try:
        out = _rt().batch_ingest(
            group_id=str(args.get("group_id")), batch_id=str(args.get("batch_id")),
            results=_json_arg(args.get("results"), []),
            attempt_id=str(args.get("attempt_id", "")),
            staging_root=str(args.get("staging_root", "")),
            project_root=str(args.get("project_root", "")),
            apply=bool(args.get("apply", False)),
        )
        return _ok(out)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_BATCH_INGEST")


BATCH_COMPLETE = _schema(
    "flow_batch_complete",
    "Mark a batch complete with score/verdict.",
    {"batch_id": {"type": "string"}, "score": {"type": "number"}, "verdict": {"type": "string"}},
    required=["batch_id"],
)


def handle_batch_complete(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().batch_complete(
        str(args.get("batch_id")), score=args.get("score"),
        verdict=str(args.get("verdict", "pass"))))


BATCH_FAIL = _schema(
    "flow_batch_fail",
    "Report batch failure; retries until max_attempts then failed.",
    {"batch_id": {"type": "string"}, "reason": {"type": "string"}}, required=["batch_id"],
)


def handle_batch_fail(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().batch_fail(str(args.get("batch_id")), str(args.get("reason", ""))))


BATCH_SPLIT = _schema(
    "flow_batch_split",
    "Split a batch in half (context overflow/truncation), bounded by max_split_depth.",
    {"batch_id": {"type": "string"}}, required=["batch_id"],
)


def handle_batch_split(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().batch_split(str(args.get("batch_id"))))


BATCH_REPAIR = _schema(
    "flow_batch_repair",
    "Create a repair sub-batch containing only failed files.",
    {"batch_id": {"type": "string"}, "failed_files": {"type": "array", "items": {"type": "string"}}},
    required=["batch_id", "failed_files"],
)


def handle_batch_repair(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().batch_repair(
        str(args.get("batch_id")), [str(x) for x in args.get("failed_files", [])]))


# ---------------------------------------------------------------------------
# Quality / recovery
# ---------------------------------------------------------------------------
GATE_SCORE = _schema(
    "flow_gate_score",
    "Batch-level quality gate (AST/diff/write-scope/scoped-tests/LLM).",
    {
        "ast_ok": {"type": "boolean"}, "diff_ok": {"type": "boolean"},
        "write_scope_ok": {"type": "boolean"}, "scoped_tests_ok": {"type": "boolean"},
        "llm_score": {"type": "number"}, "truncated": {"type": "boolean"},
    },
    required=["ast_ok", "diff_ok"],
)


def handle_gate_score(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().gate_batch(
        ast_ok=bool(args.get("ast_ok")), diff_ok=bool(args.get("diff_ok")),
        write_scope_ok=bool(args.get("write_scope_ok", True)),
        scoped_tests_ok=bool(args.get("scoped_tests_ok", True)),
        llm_score=args.get("llm_score"), truncated=bool(args.get("truncated", False))))


GATE_AGGREGATE = _schema(
    "flow_gate_aggregate",
    "Aggregate gate: full build/browser/coverage across all batches.",
    {
        "batch_scores": {"type": "array", "items": {"type": "number"}},
        "coverage": {"type": "number"},
        "full_build_ok": {"type": "boolean"},
        "browser_ok": {"type": "boolean"},
    },
    required=["batch_scores", "coverage", "full_build_ok", "browser_ok"],
)


def handle_gate_aggregate(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().gate_aggregate(
        batch_scores=[float(x) for x in args.get("batch_scores", [])],
        coverage=float(args.get("coverage", 1.0)),
        full_build_ok=bool(args.get("full_build_ok")),
        browser_ok=bool(args.get("browser_ok"))))


QUALITY_COLLECT = _schema(
    "flow_quality_collect",
    "真实质量采集：执行项目 build（npm run build / vite build）、可选 typecheck / tests / Playwright，"
    "返回逐项 ok、退出码、耗时与日志尾部，并写入 plugin-data/quality/。",
    {
        "project_root": {"type": "string", "description": "被迁移项目根目录"},
        "build": {"type": "boolean", "description": "执行构建，默认 true"},
        "typecheck": {"type": "boolean", "description": "执行类型检查，默认 true"},
        "tests": {"type": "boolean", "description": "执行 npm test，默认 false"},
        "browser": {"type": "boolean", "description": "执行 Chrome/CDP 路由验证（需已 build）"},
        "timeout": {"type": "integer", "description": "单命令/浏览器超时秒数，默认 300"},
        "routes": {"type": "array", "items": {"type": "string"}, "description": "要验证的路由，默认从 src/router 自动解析"},
    },
    required=["project_root"],
)


def handle_quality_collect(args: Dict[str, Any], **_kw) -> str:
    try:
        out = _rt().quality_collect(
            project_root=str(args.get("project_root", "")),
            build=bool(args.get("build", True)),
            typecheck=bool(args.get("typecheck", True)),
            tests=bool(args.get("tests", False)),
            browser=bool(args.get("browser", False)),
            timeout=int(args.get("timeout", 300) or 300),
            routes=[str(x) for x in args.get("routes", [])] or None,
        )
        return _ok(out)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_QUALITY_COLLECT")


RECOVERY_CLASSIFY = _schema(
    "flow_recovery_classify",
    "Classify an error into a recovery category and suggested action.",
    {"error": {"type": "string"}, "status_code": {"type": "integer"}},
)


def handle_recovery_classify(args: Dict[str, Any], **_kw) -> str:
    cat = classify(str(args.get("error", "")), int(args.get("status_code", 0) or 0))
    return _ok({"category": cat.value, "retryable": cat.value not in ("AUTH", "UNKNOWN")})


# ---------------------------------------------------------------------------
# Experience / board
# ---------------------------------------------------------------------------
EXPERIENCE_ADD = _schema(
    "flow_experience_add",
    "Persist a structured migration pitfall/experience; dedup by category+trigger.",
    {
        "category": {"type": "string"}, "trigger": {"type": "string"},
        "solution": {"type": "string"}, "phase": {"type": "string"},
        "versions": {"type": "string"},
    },
    required=["category", "trigger", "solution"],
)


def handle_experience_add(args: Dict[str, Any], **_kw) -> str:
    return _ok(_rt().experience_add(
        category=str(args.get("category")), trigger=str(args.get("trigger")),
        solution=str(args.get("solution")), phase=str(args.get("phase", "")),
        versions=str(args.get("versions", ""))))


EXPERIENCE_SEARCH = _schema(
    "flow_experience_search",
    "Search experiences by keyword/phase for injection into the next turn.",
    {"query": {"type": "string"}, "phase": {"type": "string"}, "limit": {"type": "integer"}},
)


def handle_experience_search(args: Dict[str, Any], **_kw) -> str:
    return _ok({"experiences": _rt().experience_search(
        query=str(args.get("query", "")), phase=str(args.get("phase", "")),
        limit=int(args.get("limit", 5) or 5))})


BOARD_RENDER = _schema(
    "flow_board_render",
    "Render a self-contained HTML board for runs and experiences.",
    {"title": {"type": "string"}, "out": {"type": "string"}},
)


def handle_board_render(args: Dict[str, Any], **_kw) -> str:
    out = str(args.get("out", ""))
    html = _rt().render_board(title=str(args.get("title", "HERMES Flow 迁移看板")), out=out)
    return _ok({"path": out, "size": len(html)})


QUALITY_GATE = _schema(
    "flow_quality_gate",
    "真实聚合门：执行 build/typecheck，再与批次分数/覆盖率/浏览器结果一起按 85 阈值判定。"
    "browser=false 时 browser_ok=false，聚合门会要求人工浏览器验证。",
    {
        "project_root": {"type": "string"},
        "batch_scores": {"type": "array", "items": {"type": "number"}},
        "coverage": {"type": "number", "description": "文件覆盖率，默认 1.0"},
        "browser": {"type": "boolean", "description": "执行 Chrome/CDP 路由验证（有 build 产物时）"},
        "timeout": {"type": "integer", "description": "单命令超时，默认 300"},
        "routes": {"type": "array", "items": {"type": "string"}, "description": "要验证的路由，默认自动解析"},
    },
    required=["project_root", "batch_scores"],
)


def handle_quality_gate(args: Dict[str, Any], **_kw) -> str:
    try:
        out = _rt().quality_gate(
            project_root=str(args.get("project_root")),
            batch_scores=[float(x) for x in args.get("batch_scores", [])],
            coverage=float(args.get("coverage", 1.0)),
            browser=bool(args.get("browser", False)),
            timeout=int(args.get("timeout", 300) or 300),
            routes=[str(x) for x in args.get("routes", [])] or None,
        )
        return _ok(out)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), "FLOW_QUALITY_GATE")


# ---------------------------------------------------------------------------
# Registry table
# ---------------------------------------------------------------------------
TOOL_SPECS: List[Dict[str, Any]] = [
    {"schema": AGENT_CREATE, "handler": handle_agent_create},
    {"schema": _schema("flow_agent_list", "List registered experts.", {}), "handler": handle_agent_list},
    {"schema": _schema("flow_agent_get", "Get one expert.", {"agent_id": {"type": "string"}}, ["agent_id"]),
     "handler": handle_agent_get},
    {"schema": _schema("flow_agent_update", "Update an expert.", {"agent_id": {"type": "string"}}, ["agent_id"]),
     "handler": handle_agent_update},
    {"schema": _schema("flow_agent_delete", "Delete a user expert.", {"agent_id": {"type": "string"}}, ["agent_id"]),
     "handler": handle_agent_delete},
    {"schema": SKILL_CREATE, "handler": handle_skill_create},
    {"schema": _schema("flow_skill_list", "List skills.", {}), "handler": handle_skill_list},
    {"schema": WORKFLOW_CREATE, "handler": handle_workflow_create},
    {"schema": _schema("flow_workflow_list", "List workflow templates.", {}), "handler": handle_workflow_list},
    {"schema": _schema("flow_workflow_get", "Get a workflow.", {"workflow_id": {"type": "string"}}, ["workflow_id"]),
     "handler": handle_workflow_get},
    {"schema": _schema("flow_workflow_validate", "Validate a workflow definition JSON string.",
                       {"definition": {"type": "string"}}, ["definition"]),
     "handler": handle_workflow_validate},
    {"schema": RUN_START, "handler": handle_run_start},
    {"schema": _schema("flow_run_status", "Get run status (or list runs).",
                       {"run_id": {"type": "string"}}), "handler": handle_run_status},
    {"schema": _schema("flow_run_pause", "Pause a run.", {"run_id": {"type": "string"}}, ["run_id"]),
     "handler": handle_run_pause},
    {"schema": _schema("flow_run_resume", "Resume a run.", {"run_id": {"type": "string"}}, ["run_id"]),
     "handler": handle_run_resume},
    {"schema": _schema("flow_run_cancel", "Cancel a run.", {"run_id": {"type": "string"}}, ["run_id"]),
     "handler": handle_run_cancel},
    {"schema": BATCH_PLAN, "handler": handle_batch_plan},
    {"schema": BATCH_NEXT, "handler": handle_batch_next},
    {"schema": BATCH_AUTO, "handler": handle_batch_auto},
    {"schema": BATCH_STATUS, "handler": handle_batch_status},
    {"schema": BATCH_ITEMS, "handler": handle_batch_items},
    {"schema": BATCH_INGEST, "handler": handle_batch_ingest},
    {"schema": BATCH_COMPLETE, "handler": handle_batch_complete},
    {"schema": BATCH_FAIL, "handler": handle_batch_fail},
    {"schema": BATCH_SPLIT, "handler": handle_batch_split},
    {"schema": BATCH_REPAIR, "handler": handle_batch_repair},
    {"schema": GATE_SCORE, "handler": handle_gate_score},
    {"schema": GATE_AGGREGATE, "handler": handle_gate_aggregate},
    {"schema": QUALITY_COLLECT, "handler": handle_quality_collect},
    {"schema": QUALITY_GATE, "handler": handle_quality_gate},
    {"schema": RECOVERY_CLASSIFY, "handler": handle_recovery_classify},
    {"schema": EXPERIENCE_ADD, "handler": handle_experience_add},
    {"schema": EXPERIENCE_SEARCH, "handler": handle_experience_search},
    {"schema": BOARD_RENDER, "handler": handle_board_render},
]


def register_tools(ctx) -> None:
    for spec in TOOL_SPECS:
        schema = spec["schema"]
        ctx.register_tool(name=schema["name"], toolset=TOOLSET,
                          schema=schema, handler=spec["handler"])
