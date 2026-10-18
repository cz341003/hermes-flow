"""工作流编排器：DAG 顺序执行 + batch 节点展开为批次队列。

这是"确定性执行壳"：runner 由调用方注入（生产环境为插件工具/子代理，
测试/CLI demo 可用 mock runner）。真正的 LLM 驱动由 Hermes agent turn 完成，
本编排器负责状态、批次、门控与报告。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .batch import BatchPolicy, BatchQueue, FileItem, plan_batches
from .batch.models import BatchRecord
from .engine.dag import Node, Workflow, topological_sort
from .engine.scheduler import ExecutionResult
from .quality.batch_gate import aggregate_gate, evaluate_batch

Runner = Callable[[Node, Dict[str, Any]], ExecutionResult]


@dataclass
class RunResult:
    run_id: str
    done: bool
    trace: List[str] = field(default_factory=list)
    node_states: Dict[str, str] = field(default_factory=dict)
    batches: Dict[str, Any] = field(default_factory=dict)
    aggregate: Dict[str, Any] = field(default_factory=dict)
    failed_nodes: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id, "done": self.done, "trace": self.trace,
            "node_states": self.node_states, "batches": self.batches,
            "aggregate": self.aggregate, "failed_nodes": self.failed_nodes,
            "reason": self.reason,
        }


class WorkflowOrchestrator:
    def __init__(self, batch_queue: BatchQueue, *, default_policy: Optional[BatchPolicy] = None):
        self.queue = batch_queue
        self.default_policy = default_policy or BatchPolicy()

    # ------------------------------------------------------------------
    def run(self, workflow_def: Dict[str, Any], runner: Runner, *,
            run_id: str = "", project_root: str = "",
            files_by_node: Optional[Dict[str, List[Dict[str, Any]]]] = None,
            expert_policies: Optional[Dict[str, Dict[str, Any]]] = None,
            max_steps: int = 1000) -> RunResult:
        run_id = run_id or f"run-{int(time.time())}"
        nodes = workflow_def.get("nodes") or []
        edges = workflow_def.get("edges") or []
        simple_nodes = [{
            "id": n["id"], "name": n.get("name", n["id"]),
            "phase": n.get("phase", "transform"), "agent": n.get("agent", ""),
            "skill": n.get("skill"), "parallel": bool(n.get("parallel", False)),
        } for n in nodes]
        wf = Workflow.from_dict({"id": workflow_def.get("id", run_id),
                                 "name": workflow_def.get("name", run_id),
                                 "nodes": simple_nodes, "edges": edges})
        order = topological_sort(wf)
        node_map = {n["id"]: n for n in nodes}
        files_by_node = files_by_node or {}
        expert_policies = expert_policies or {}

        result = RunResult(run_id=run_id, done=True)
        batch_scores: List[float] = []
        coverage_values: List[float] = []
        steps = 0
        for node_id in order:
            steps += 1
            if steps > max_steps:
                result.done = False
                result.reason = "超过 max_steps，可能死循环"
                break
            node = wf.node(node_id)
            raw = node_map.get(node_id, {})
            ntype = str(raw.get("type", "agent_task"))
            result.trace.append(node_id)
            if ntype == "batch":
                files = self._files_for_node(node_id, raw, files_by_node)
                policy = BatchPolicy.from_loop_policy(
                    expert_policies.get(str(raw.get("agent", "")), {}).get("loop_policy")
                    or raw.get("batch")
                )
                gid = self.queue.create_group(
                    plan=plan_batches([FileItem.from_dict(f) for f in files], policy),
                    run_id=run_id, node_id=node_id,
                    expert_id=str(raw.get("agent", "")), policy=policy,
                )
                ok = self._run_batch_group(gid, node, runner, run_id, project_root, policy)
                status = self.queue.status(gid)
                result.batches[node_id] = status
                scores = [b["score"] for b in status["batches"] if b.get("score") is not None]
                batch_scores.extend(scores)
                total = status["total_batches"]
                done = status["done_batches"]
                coverage_values.append(done / total if total else 1.0)
                result.node_states[node_id] = "done" if ok else "failed"
                if not ok:
                    result.done = False
                    result.failed_nodes.append(node_id)
            else:
                ctx = {
                    "run_id": run_id, "node": node, "node_def": raw,
                    "project_root": project_root,
                }
                res = runner(node, ctx)
                result.node_states[node_id] = "done" if res.success else "failed"
                if not res.success:
                    result.done = False
                    result.failed_nodes.append(node_id)
        coverage = min(coverage_values) if coverage_values else 1.0
        avg_scores = batch_scores
        result.aggregate = aggregate_gate(
            batch_scores=avg_scores, coverage=coverage,
            full_build_ok=result.done, browser_ok=result.done,
        ) if batch_scores else {"score": 0.0, "verdict": "pass" if result.done else "rework",
                                "coverage": coverage, "reasons": []}
        if result.aggregate.get("verdict") != "pass":
            result.done = False
            if not result.reason:
                result.reason = "聚合门未通过"
        return result

    # ------------------------------------------------------------------
    def _files_for_node(self, node_id: str, raw: Dict[str, Any],
                        files_by_node: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if node_id in files_by_node:
            return files_by_node[node_id]
        batch_cfg = raw.get("batch") or {}
        inline = batch_cfg.get("files")
        if isinstance(inline, list):
            return inline
        return []

    # ------------------------------------------------------------------
    def _run_batch_group(self, group_id: str, node: Node, runner: Runner,
                         run_id: str, project_root: str, policy: BatchPolicy) -> bool:
        status0 = self.queue.status(group_id)
        total_files = sum(len(b.get("files") or []) for b in status0["batches"])
        max_loops = max(50, total_files * 3 + status0["total_batches"] * 3)
        for _ in range(max_loops):
            status = self.queue.status(group_id)
            if status["failed"]:
                return False
            if status["done_batches"] >= status["total_batches"] and not status["running"]:
                return True
            batch = self.queue.claim_next(group_id, "orchestrator")
            if batch is None:
                # 有 running（等租约）或 ready 但暂不可认领 → 交给上层 tick 重试
                return False
            ctx = {
                "run_id": run_id, "node": node,
                "batch": batch.to_dict(), "files": batch.files,
                "project_root": project_root, "staging_root": "",
                "policy": policy.to_dict(),
            }
            res = runner(node, ctx)
            if res.truncated and policy.split_on_failure:
                new_ids = self.queue.split(batch.id)
                if new_ids:
                    continue
            if res.success:
                # 先回灌逐文件结果（staged），再完成批次（staged→applied）
                self.queue.ingest(batch.id, [{"path": f["path"], "status": "done"}
                                             for f in batch.files],
                                  attempt_id=str(batch.attempt))
                score = float(res.score if res.score is not None else 90.0)
                verdict = "pass" if score >= 85 else ("warn" if score >= 70 else "rework")
                if verdict == "rework":
                    failed = [f["path"] for f in batch.files]
                    repair_id = self.queue.repair(batch.id, failed)
                    if repair_id:
                        # 原批标记完成（其文件已由 repair 接手），避免卡住 wave
                        self.queue.complete(batch.id, score=score, verdict="rework")
                        continue
                    self.queue.fail(batch.id, "batch gate rework（repair 上限）")
                    continue
                self.queue.complete(batch.id, score=score, verdict=verdict)
            else:
                self.queue.fail(batch.id, res.error or "batch runner failed")
        return False
