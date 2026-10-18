"""HERMES Flow 端到端 demo：真实 20 文件 Vue2 小项目 → 批次规划 → mock 转化
→ ingest → apply（staging→工作区 + 备份）→ 质量门 → 输出 JSON 报告。

运行（cwd 任意，脚本自行定位插件根目录）：

    python tests/e2e_demo.py

产物：``tests/out/e2e-report.json``；最后断言 ``done=True``、全部批次 done、
20 个文件全部 applied 且 applied_hash 与工作区文件一致。

mock 转化 = 读取源文件 → 按扩展名加迁移标记后写入 staging（模拟子代理产出），
不调用任何 LLM，因此该 demo 可用于 CI 回归。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow_core.batch import (  # noqa: E402
    BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches,
)
from flow_core.quality.batch_gate import aggregate_gate, evaluate_batch  # noqa: E402

TMP_BASE = Path(os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
SAMPLE_APP = ROOT.parent / "sample-app"
REPORT_PATH = ROOT / "tests" / "out" / "e2e-report.json"
GROUP_ID = "g-e2e-demo"
RUN_ID = "run-e2e-demo"

# 真实 Vue2 项目的依赖关系（相对 posix 路径）
DEPS: dict[str, list[str]] = {
    "src/utils/format.js": [],
    "src/utils/request.js": [],
    "src/mixins/loadingMixin.js": [],
    "src/styles/variables.less": [],
    "src/styles/global.less": ["src/styles/variables.less"],
    "src/store/modules/user.js": ["src/utils/request.js"],
    "src/store/index.js": ["src/store/modules/user.js"],
    "src/components/HelloWorld.vue": ["src/mixins/loadingMixin.js", "src/utils/format.js"],
    "src/components/UserCard.vue": ["src/mixins/loadingMixin.js", "src/utils/format.js"],
    "src/components/TreeMenu.vue": ["src/utils/format.js"],
    "src/views/Home.vue": ["src/components/HelloWorld.vue", "src/utils/request.js"],
    "src/views/About.vue": ["src/components/UserCard.vue"],
    "src/views/UserList.vue": ["src/components/UserCard.vue", "src/store/modules/user.js",
                               "src/utils/request.js"],
    "src/router/index.js": ["src/views/Home.vue", "src/views/About.vue", "src/views/UserList.vue"],
    "src/App.vue": ["src/components/TreeMenu.vue"],
    "src/main.js": ["src/App.vue", "src/router/index.js", "src/store/index.js"],
    "index.html": ["src/main.js"],
    "webpack.config.js": ["babel.config.js", "package.json"],
    "babel.config.js": [],
    "package.json": [],
}
HIGH_RISK = {"src/router/index.js", "src/store/index.js"}

MARKERS = {
    ".js": "// HERMES-FLOW: migrated Vue2 -> Vue3\n",
    ".vue": "// HERMES-FLOW: migrated Vue2 -> Vue3\n",
    ".less": "/* HERMES-FLOW: migrated Vue2 -> Vue3 */\n",
    ".html": "<!-- HERMES-FLOW: migrated Vue2 -> Vue3 -->\n",
}

PACKAGE_JSON = """{
  "name": "hermes-flow-e2e-app",
  "version": "1.0.0",
  "private": true
}
"""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# 1. 准备真实小项目
# ---------------------------------------------------------------------------
def prepare_project(tmp_root: Path) -> tuple[Path, list[Path]]:
    if SAMPLE_APP.is_dir():
        files = sorted(p for p in SAMPLE_APP.rglob("*") if p.is_file())
        project = tmp_root / "project"
        shutil.copytree(SAMPLE_APP, project)
        rels = [p.relative_to(SAMPLE_APP).as_posix() for p in files]
        return project, [project / rel for rel in rels]

    # 兜底：sample-app 不存在时合成同结构的 20 文件小项目
    project = tmp_root / "project"
    contents = {
        "package.json": PACKAGE_JSON,
        "babel.config.js": "module.exports = { presets: ['@vue/cli-plugin-babel/preset'] }\n",
        "webpack.config.js": "module.exports = { mode: 'development' }\n",
        "index.html": "<div id=\"app\"></div>\n",
    }
    for rel in DEPS:
        if rel in contents:
            continue
        suffix = Path(rel).suffix
        name = Path(rel).stem
        if suffix == ".vue":
            contents[rel] = (f"<template><div class=\"{name}\">{{{{ msg }}}}</div></template>\n"
                             f"<script>export default {{ data() {{ return {{ msg: '{name}' }} }} }}</script>\n")
        elif suffix == ".less":
            contents[rel] = f"@{name}: 1px;\n.{name} {{ color: #333; }}\n"
        else:
            contents[rel] = f"// {name}\nexport default {{ name: '{name}' }}\n"
    for rel, text in contents.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    files = sorted(p for p in project.rglob("*") if p.is_file())
    return project, files


def build_items(project: Path, files: list[Path]) -> list[FileItem]:
    items = []
    for path in sorted(files):
        rel = path.relative_to(project).as_posix()
        items.append(FileItem(
            path=rel,
            size=path.stat().st_size,
            deps=DEPS.get(rel, []),
            risk="high" if rel in HIGH_RISK else "low",
            sha256=_sha256(path.read_bytes()),
        ))
    return items


# ---------------------------------------------------------------------------
# 2. mock 转化：源文件 → staging（加迁移标记）
# ---------------------------------------------------------------------------
def mock_transform(project: Path, staging_root: Path, rel: str) -> Path:
    source = project / rel
    raw = source.read_bytes()
    marker = MARKERS.get(source.suffix, "")
    data = raw if not marker else marker.encode("utf-8") + raw
    dst = staging_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return dst


def expected_content(project: Path, rel: str) -> bytes:
    raw = (project / rel).read_bytes()
    marker = MARKERS.get(Path(rel).suffix, "")
    return raw if not marker else marker.encode("utf-8") + raw


# ---------------------------------------------------------------------------
# 3. 主流程
# ---------------------------------------------------------------------------
def run_demo() -> dict:
    TMP_BASE.mkdir(parents=True, exist_ok=True)
    tmp_root = Path(tempfile.mkdtemp(dir=str(TMP_BASE)))
    started = time.time()
    project, files = prepare_project(tmp_root)
    items = build_items(project, files)
    assert len(items) == 20, f"demo 需要 20 个文件，实际 {len(items)}"
    expected_bytes = {item.path: expected_content(project, item.path) for item in items}

    policy = BatchPolicy(max_files_per_batch=5, context_budget_chars=28000,
                         max_split_depth=2, max_attempts=3)
    plan = plan_batches(items, policy)
    assert plan.total_files == 20
    assert plan.waves >= 3, "真实项目应产生多 wave 依赖分层"

    staging_root = tmp_root / "staging"
    backup_root = tmp_root / "backup"
    staging_root.mkdir(parents=True, exist_ok=True)

    store = BatchStore(tmp_root / "batches.db")
    queue = BatchQueue(store, policy)
    try:
        group_id = queue.create_group(
            plan=plan, run_id=RUN_ID, node_id="transform",
            expert_id="code-transformer", group_id=GROUP_ID, policy=policy)

        batch_reports = []
        gate_scores: list[float] = []
        while True:
            batch = queue.claim_next(group_id, "e2e-runner")
            if batch is None:
                break
            staging = staging_root / batch.id
            results = []
            for item in batch.files:
                rel = item["path"]
                dst = mock_transform(project, staging, rel)
                results.append({"path": rel, "status": "done", "staged_path": str(dst)})

            ingest = queue.ingest(batch.id, results, attempt_id=str(batch.attempt),
                                  staging_root=str(staging), project_root=str(project))
            assert not ingest["missing"], f"ingest missing: {ingest['missing']}"
            assert not ingest["failed"], f"ingest failed: {ingest['failed']}"

            gate = evaluate_batch(ast_ok=True, diff_ok=True, write_scope_ok=True,
                                  scoped_tests_ok=True, llm_score=92)
            assert gate["verdict"] == "pass", f"批级质量门未通过: {gate}"

            apply_result = queue.apply(batch.id, project_root=str(project),
                                       staging_root=str(staging), backup_root=str(backup_root / batch.id))
            assert apply_result["errors"] == [], f"apply errors: {apply_result['errors']}"
            assert apply_result["missing"] == [], f"apply missing: {apply_result['missing']}"
            assert len(apply_result["applied"]) == len(batch.files), \
                f"apply 数量不符: {apply_result['applied']} vs {len(batch.files)}"

            queue.complete(batch.id, score=gate["score"], verdict="pass")
            gate_scores.append(gate["score"])
            batch_reports.append({
                "id": batch.id, "wave": batch.wave, "files": [f["path"] for f in batch.files],
                "attempt": batch.attempt, "status": "done",
                "score": gate["score"], "applied": apply_result["applied"],
            })

        status = queue.status(group_id)
        status_batches = status["batches"]
        failed = status["failed"]
        ready = status["ready"]
        running = status["running"]

        # 逐文件校验 applied + hash + 内容
        applied_files = []
        items_by_path = {}
        for batch in status_batches:
            for item in store.list_items(batch["id"]):
                if item.status == "applied":
                    items_by_path[item.file_path] = item
        for item in items:
            record = items_by_path.get(item.path)
            assert record is not None, f"文件未 applied: {item.path}"
            actual = (project / item.path).read_bytes()
            assert record.applied_hash == _sha256(actual), f"applied_hash 不一致: {item.path}"
            assert actual == expected_bytes[item.path], \
                f"工作区内容不是 mock 转化结果: {item.path}"
            applied_files.append({
                "path": item.path,
                "applied_hash": record.applied_hash,
                "bytes": len(actual),
            })

        # 重复 apply 幂等：对第一批再 apply 一次，hash 不变、不报错
        first_done = next(b for b in status_batches if b["status"] == "done")
        before = {i.file_path: i.applied_hash for i in store.list_items(first_done["id"])}
        again = queue.apply(first_done["id"], project_root=str(project),
                            staging_root=str(staging_root / first_done["id"]),
                            backup_root=str(backup_root / "idempotent"))
        after = {i.file_path: i.applied_hash for i in store.list_items(first_done["id"])}
        idempotent_ok = (again["errors"] == [] and before == after)
        assert idempotent_ok, f"重复 apply 非幂等: {before} -> {after}, {again}"

        coverage = status["done_batches"] / status["total_batches"] if status["total_batches"] else 1.0
        aggregate = aggregate_gate(batch_scores=gate_scores, coverage=coverage,
                                   full_build_ok=True, browser_ok=True)
        done = (
            status["done_batches"] == status["total_batches"]
            and not failed and not ready and not running
            and len(applied_files) == len(items)
            and aggregate["verdict"] == "pass"
        )
        assert done, f"e2e 未 done: status={status}, aggregate={aggregate}"

        elapsed = round(time.time() - started, 3)
        report = {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "demo": "HERMES Flow e2e (mock transform, real apply)",
            "plugin_root": str(ROOT),
            "plugin_version": _plugin_version(),
            "project": str(project),
            "sample_app": str(SAMPLE_APP) if SAMPLE_APP.is_dir() else "(generated fallback)",
            "run_id": RUN_ID,
            "group_id": group_id,
            "done": done,
            "elapsed_seconds": elapsed,
            "policy": policy.to_dict(),
            "plan": {
                "total_files": plan.total_files,
                "total_batches": plan.total_batches,
                "waves": plan.waves,
                "high_risk_files": sorted(HIGH_RISK),
                "batches": [
                    {"id": b.id, "wave": b.wave, "priority": b.priority,
                     "files": [f.path for f in b.files]}
                    for b in plan.batches
                ],
            },
            "gate": {"per_batch_scores": gate_scores,
                     "average": round(sum(gate_scores) / len(gate_scores), 2),
                     "aggregate": aggregate},
            "status": {
                "total_batches": status["total_batches"],
                "done_batches": status["done_batches"],
                "failed_batches": failed,
                "ready_batches": ready,
                "running_batches": running,
                "item_status_counts": status["items"],
            },
            "batches": batch_reports,
            "applied_files": applied_files,
            "checks": {
                "all_batches_done": status["done_batches"] == status["total_batches"],
                "no_failed_batches": not failed,
                "all_20_files_applied": len(applied_files) == len(items),
                "applied_hash_matches_workspace": True,
                "aggregate_gate_pass": aggregate["verdict"] == "pass",
                "idempotent_apply": idempotent_ok,
                "high_risk_isolated": all(
                    len(b.files) == 1 for b in plan.batches
                    if any(f.risk == "high" for f in b.files)),
            },
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        return report
    finally:
        store.close()
        shutil.rmtree(tmp_root, ignore_errors=True)


def _plugin_version() -> str:
    try:
        import flow_core  # noqa: F401
        return str(getattr(flow_core, "__version__", "unknown"))
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    report = run_demo()
    print("=" * 66)
    print("HERMES Flow 端到端 demo")
    print(f"  文件: {report['plan']['total_files']}  批次: {report['plan']['total_batches']}  "
          f"waves: {report['plan']['waves']}")
    print(f"  批次状态: {report['status']['done_batches']}/{report['status']['total_batches']} done, "
          f"failed={report['status']['failed_batches']}")
    print(f"  聚合门: {report['gate']['aggregate']['verdict']}  "
          f"score={report['gate']['aggregate']['score']}  "
          f"coverage={report['gate']['aggregate']['coverage']}")
    print(f"  applied 文件: {len(report['applied_files'])}")
    print(f"  幂等 apply: {report['checks']['idempotent_apply']}")
    print(f"  done = {report['done']}")
    print(f"  报告: {REPORT_PATH}")
    print("=" * 66)
    return 0 if report["done"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
