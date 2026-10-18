"""WorkflowOrchestrator 独立测试：6 阶段模板 + mock runner。

覆盖：
- 6 阶段（batch 节点 + 普通节点）跑通、report done、聚合门 pass；
- batch 节点 policy（节点 batch 配置 / 专家 loop_policy）生效；
- 批次失败触发 fail（done=False）；
- 普通节点失败 → done=False；
- truncated 触发 split，拆到底后最终 report done；
- max_split_depth 用尽边界：不提前放弃、不留 ready/running 批次。
"""
from __future__ import annotations

import shutil
import sys
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow_core.batch import BatchQueue, BatchStore  # noqa: E402
from flow_core.engine.scheduler import ExecutionResult  # noqa: E402
from flow_core.orchestrator import WorkflowOrchestrator  # noqa: E402

TMP_BASE = Path(os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())


def six_phase_workflow(batch_cfg: dict | None = None) -> dict:
    transform = {
        "id": "transform", "name": "转化", "phase": "transform", "type": "batch",
        "agent": "code-transformer",
        "batch": batch_cfg or {"max_files_per_batch": 3, "max_split_depth": 2},
    }
    return {
        "id": "wf-6phase",
        "name": "六阶段迁移",
        "nodes": [
            {"id": "analyze", "name": "分析", "phase": "analyze", "type": "agent_task",
             "agent": "structure-analyst"},
            {"id": "deps", "name": "依赖", "phase": "deps", "type": "agent_task",
             "agent": "dependency-analyst"},
            transform,
            {"id": "quality", "name": "质量", "phase": "quality", "type": "quality_gate"},
            {"id": "verify", "name": "验证", "phase": "verify", "type": "agent_task",
             "agent": "code-transformer"},
            {"id": "fix", "name": "修复", "phase": "fix", "type": "agent_task",
             "agent": "fix-specialist"},
        ],
        "edges": [
            {"source": "analyze", "target": "deps"},
            {"source": "deps", "target": "transform"},
            {"source": "transform", "target": "quality"},
            {"source": "quality", "target": "verify"},
            {"source": "verify", "target": "fix"},
        ],
    }


def make_files(count: int, prefix: str = "src/f") -> list:
    return [{"path": f"{prefix}{i}.vue", "size": 600, "deps": []} for i in range(count)]


class MockRunner:
    """可编程 mock runner：记录调用，按节点/批次返回结果。"""

    def __init__(self, *, score: float = 92.0, node_failures: set | None = None,
                 batch_failures: bool = False, truncated_times: int = 0):
        self.score = score
        self.node_failures = node_failures or set()
        self.batch_failures = batch_failures
        self.truncated_times = truncated_times
        self.calls: list = []

    def __call__(self, node, ctx):
        is_batch = "batch" in ctx
        self.calls.append({
            "node": node.id, "is_batch": is_batch,
            "batch_id": (ctx.get("batch") or {}).get("id"),
            "files": list(ctx.get("files") or []),
            "policy": dict(ctx.get("policy") or {}),
        })
        if is_batch:
            if self.batch_failures:
                return ExecutionResult(success=False, error=f"{node.id}: boom")
            if self.truncated_times > 0:
                self.truncated_times -= 1
                return ExecutionResult(success=True, score=self.score, truncated=True)
            return ExecutionResult(success=True, score=self.score)
        if node.id in self.node_failures:
            return ExecutionResult(success=False, error=f"{node.id}: boom")
        return ExecutionResult(success=True, score=self.score)


class OrchestratorTestBase(unittest.TestCase):
    def setUp(self) -> None:
        TMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=str(TMP_BASE)))
        self.store = BatchStore(self.tmp / "batch.db")
        self.queue = BatchQueue(self.store)
        self.orch = WorkflowOrchestrator(self.queue)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def tearDown(self) -> None:
        self.store.close()

    def run_workflow(self, workflow: dict, runner, files: list | None = None, **kwargs):
        return self.orch.run(workflow, runner, run_id=kwargs.pop("run_id", "run-test"),
                             files_by_node={"transform": files or []}, **kwargs)


class HappyPathTest(OrchestratorTestBase):
    def test_six_phase_template_runs_to_done(self) -> None:
        runner = MockRunner(score=92)
        result = self.run_workflow(six_phase_workflow(), runner, make_files(7))
        self.assertTrue(result.done, f"6 阶段应跑通, reason={result.reason}")
        self.assertEqual(
            result.trace,
            ["analyze", "deps", "transform", "quality", "verify", "fix"])
        self.assertEqual(set(result.node_states), set(result.trace))
        self.assertTrue(all(v == "done" for v in result.node_states.values()))
        self.assertEqual(result.failed_nodes, [])
        self.assertEqual(result.aggregate["verdict"], "pass")
        self.assertEqual(result.aggregate["coverage"], 1.0)

        status = result.batches["transform"]
        self.assertEqual(status["total_batches"], 3)  # 7 文件 / 每批 3
        self.assertEqual(status["done_batches"], status["total_batches"])
        self.assertEqual(status["failed"], [])
        self.assertEqual(status["ready"], [])
        self.assertEqual(status["running"], [])
        # mock runner 每个批次都被调用，且每批文件数 ≤ 策略上限
        batch_calls = [c for c in runner.calls if c["is_batch"]]
        self.assertEqual(len(batch_calls), 3)
        self.assertTrue(all(1 <= len(c["files"]) <= 3 for c in batch_calls))
        # 成功批次应先 ingest 再 complete → 逐文件 applied
        for batch in status["batches"]:
            items = self.store.list_items(batch["id"])
            self.assertTrue(items)
            self.assertTrue(all(i.status == "applied" for i in items),
                            f"批次 {batch['id']} 的文件未 applied: "
                            f"{[(i.file_path, i.status) for i in items]}")

    def test_batch_policy_from_node_definition(self) -> None:
        runner = MockRunner()
        result = self.run_workflow(
            six_phase_workflow({"max_files_per_batch": 2}), runner, make_files(7))
        status = result.batches["transform"]
        self.assertEqual(status["total_batches"], 4)  # ceil(7/2)
        batch_calls = [c for c in runner.calls if c["is_batch"]]
        self.assertTrue(all(c["policy"].get("max_files_per_batch") == 2 for c in batch_calls))

    def test_batch_policy_from_expert_loop_policy(self) -> None:
        runner = MockRunner()
        result = self.orch.run(
            six_phase_workflow({"max_files_per_batch": 3}), runner,
            run_id="run-expert", files_by_node={"transform": make_files(7)},
            expert_policies={"code-transformer": {
                "loop_policy": {"max_files_per_batch": 5}}})
        self.assertEqual(result.batches["transform"]["total_batches"], 2)


class FailurePathTest(OrchestratorTestBase):
    def test_batch_failure_sets_run_failed(self) -> None:
        runner = MockRunner(batch_failures=True)
        result = self.run_workflow(six_phase_workflow(), runner, make_files(4))
        self.assertFalse(result.done, "批次失败时 run 必须 done=False")
        self.assertIn("transform", result.failed_nodes)
        self.assertEqual(result.node_states["transform"], "failed")
        status = result.batches["transform"]
        self.assertTrue(status["failed"], "重试耗尽后应有 failed 批次")
        self.assertEqual(status["done_batches"], 0)
        self.assertEqual(result.aggregate["verdict"], "rework")

    def test_normal_node_failure_sets_run_failed(self) -> None:
        runner = MockRunner(node_failures={"verify"})
        result = self.run_workflow(six_phase_workflow(), runner, make_files(3))
        self.assertFalse(result.done)
        self.assertEqual(result.node_states["verify"], "failed")
        self.assertIn("verify", result.failed_nodes)
        self.assertEqual(result.node_states["transform"], "done")
        self.assertEqual(result.aggregate["verdict"], "rework")


class SplitPathTest(OrchestratorTestBase):
    def test_truncated_triggers_split_and_final_done(self) -> None:
        runner = MockRunner(score=90, truncated_times=1)
        result = self.run_workflow(
            six_phase_workflow({"max_files_per_batch": 4, "max_split_depth": 2}),
            runner, make_files(4))
        self.assertTrue(result.done, f"split 后应最终 done, reason={result.reason}")
        status = result.batches["transform"]
        batches = {b["id"]: b for b in status["batches"]}
        split_parents = [b for b in batches.values() if b["status"] == "split"]
        self.assertEqual(len(split_parents), 1, "原始批次应被标记为 split")
        self.assertEqual(len(status["batches"]), 3, "4 文件二分应产生 2 个子批")
        for child in batches.values():
            if child["id"] != split_parents[0]["id"]:
                self.assertEqual(child["status"], "done")
        self.assertEqual(status["done_batches"], status["total_batches"])
        self.assertEqual(result.aggregate["coverage"], 1.0)
        self.assertEqual(result.aggregate["verdict"], "pass")

    def test_split_depth_limited_by_node_policy(self) -> None:
        """batch.max_split_depth=1 时最多拆 1 层，拆出的 2 个批应全部完成。"""
        runner = MockRunner(score=90, truncated_times=999)  # 永远截断
        result = self.run_workflow(
            six_phase_workflow({"max_files_per_batch": 4, "max_split_depth": 1}),
            runner, make_files(4))
        status = result.batches["transform"]
        depths = [b["split_depth"] for b in status["batches"]]
        self.assertLessEqual(max(depths), 1,
                             f"节点 policy 的 max_split_depth=1 未生效: depths={depths}")
        leaves = [b for b in status["batches"] if b["status"] != "split"]
        self.assertTrue(all(b["status"] == "done" for b in leaves),
                        [(b["id"], b["status"]) for b in leaves])
        self.assertEqual(status["ready"], [])
        self.assertEqual(status["running"], [])
        self.assertTrue(result.done, f"拆到底后所有叶子批次完成应 done=True, reason={result.reason}")

    def test_max_split_depth_exhausted_completes_all_leaves(self) -> None:
        """depth=2、4 文件：需要 1+2+4 次认领，循环上限不能按初始批次数截断。"""
        runner = MockRunner(score=90, truncated_times=999)
        result = self.run_workflow(
            six_phase_workflow({"max_files_per_batch": 4, "max_split_depth": 2}),
            runner, make_files(4))
        status = result.batches["transform"]
        self.assertLessEqual(max(b["split_depth"] for b in status["batches"]), 2)
        self.assertEqual(status["ready"], [], "split 后不应留下未认领的 ready 批次")
        self.assertEqual(status["running"], [])
        leaves = [b for b in status["batches"] if b["status"] != "split"]
        self.assertEqual(len(leaves), 4, "4 文件在 depth=2 应产生 4 个叶子批")
        self.assertTrue(all(b["status"] == "done" for b in leaves),
                        [(b["id"], b["status"]) for b in leaves])
        self.assertTrue(result.done, f"所有叶子批次完成应 done=True, reason={result.reason}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
