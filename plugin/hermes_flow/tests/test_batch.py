"""批次子系统独立测试：planner / 质量门 / BatchStore+BatchQueue 生命周期 / apply。

覆盖 PRD FR-10 与边界：287 文件多 wave 无依赖倒置、预算/上限、高风险单批、
claim 原子、重试、split 二分、repair、ingest failed/missing、
staging→工作区 apply（备份/applied_hash/幂等）、lease 过期、空/单文件/超大文件。
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import os
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow_core.batch import (  # noqa: E402
    BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches,
)
from flow_core.quality.batch_gate import aggregate_gate, evaluate_batch  # noqa: E402

TMP_BASE = Path(os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# planner
# ---------------------------------------------------------------------------
class PlannerTest(unittest.TestCase):
    def _build_287(self) -> list:
        items = []
        utils = [f"src/utils/u{i}.js" for i in range(20)]
        comps = [f"src/components/c{i}.vue" for i in range(200)]
        views = [f"src/views/v{i}.vue" for i in range(67)]
        for i, path in enumerate(utils):
            items.append(FileItem(path=path, size=400 + i * 13,
                                  risk="high" if i % 17 == 0 else "low"))
        for i, path in enumerate(comps):
            items.append(FileItem(path=path, size=900 + (i * 37) % 4000,
                                  deps=[utils[i % len(utils)]],
                                  risk="high" if i % 17 == 0 else "low"))
        for i, path in enumerate(views):
            items.append(FileItem(path=path, size=1200 + (i * 53) % 5000,
                                  deps=[comps[i % len(comps)],
                                        comps[(i * 3) % len(comps)]],
                                  risk="high" if i % 17 == 0 else "low"))
        self.assertEqual(len(items), 287)
        return items

    def test_287_files_multiwave_no_dependency_inversion(self) -> None:
        items = self._build_287()
        plan = plan_batches(items, BatchPolicy(max_files_per_batch=7))
        self.assertEqual(plan.total_files, 287)
        self.assertGreater(plan.total_batches, 287 // 7)
        self.assertGreaterEqual(plan.waves, 3, "utils→components→views 至少 3 个 wave")

        seen: list = []
        batch_of: dict = {}
        for batch in plan.batches:
            self.assertGreaterEqual(len(batch.files), 1)
            self.assertLessEqual(len(batch.files), min(7, BatchPolicy().max_batch_size_cap))
            for item in batch.files:
                self.assertNotIn(item.path, batch_of, f"文件重复入批: {item.path}")
                batch_of[item.path] = batch
                seen.append(item.path)
        self.assertEqual(sorted(seen), sorted(i.path for i in items))

        # 依赖的批次 wave 必须严格早于自身（等级 = 1 + max(dep level)）
        by_path = {i.path: i for i in items}
        for item in items:
            for dep in item.deps:
                if dep not in by_path:
                    continue
                self.assertLessEqual(batch_of[dep].wave, batch_of[item.path].wave,
                                     f"依赖倒置: {dep} → {item.path}")
                self.assertLess(batch_of[dep].wave, batch_of[item.path].wave,
                                f"直接依赖应在更早 wave: {dep} → {item.path}")
        # 批次 id/seq 唯一且单调
        self.assertEqual(len({b.id for b in plan.batches}), plan.total_batches)
        self.assertEqual([b.seq for b in plan.batches],
                         sorted(b.seq for b in plan.batches))

    def test_high_risk_file_isolated(self) -> None:
        items = [FileItem(f"src/f{i}.js", size=100,
                          risk="high" if i in (2, 5) else "low") for i in range(8)]
        plan = plan_batches(items, BatchPolicy(max_files_per_batch=7))
        high_paths = {i.path for i in items if i.risk == "high"}
        for batch in plan.batches:
            risky = [f.path for f in batch.files if f.path in high_paths]
            if risky:
                self.assertEqual(len(batch.files), 1,
                                 f"高风险文件必须单独成批: {risky} 与 "
                                 f"{[f.path for f in batch.files if f.path not in high_paths]} 同批")
                self.assertEqual(batch.priority, "high")
        covered = {f.path for b in plan.batches for f in b.files}
        self.assertTrue(high_paths <= covered)

    def test_budget_packing_respects_context_budget(self) -> None:
        items = [FileItem(f"src/b{i}.js", size=2000) for i in range(5)]
        policy = BatchPolicy(max_files_per_batch=7, context_budget_chars=9000)
        plan = plan_batches(items, policy)
        for batch in plan.batches:
            cost = sum(f.size * 1.2 + 2000 for f in batch.files)
            if len(batch.files) > 1:
                self.assertLessEqual(cost, policy.context_budget_chars,
                                     f"超预算批次: {[f.path for f in batch.files]}")
        # 单文件估算 (2000*1.2+2000)=4400，两个 8800 可装，第三个 13200 超预算 → 3 批
        self.assertEqual(plan.total_batches, 3)

    def test_max_batch_size_cap(self) -> None:
        items = [FileItem(f"src/c{i}.js", size=100) for i in range(7)]
        policy = BatchPolicy(max_files_per_batch=10, max_batch_size_cap=3)
        plan = plan_batches(items, policy)
        self.assertEqual(plan.total_batches, 3)
        self.assertTrue(all(len(b.files) <= 3 for b in plan.batches))

    def test_single_oversized_file_gets_own_batch(self) -> None:
        items = [FileItem("src/huge.vue", size=10_000_000),
                 FileItem("src/a.js", size=100), FileItem("src/b.js", size=100)]
        plan = plan_batches(items, BatchPolicy(max_files_per_batch=7))
        huge = [b for b in plan.batches if any(f.path == "src/huge.vue" for f in b.files)]
        self.assertEqual(len(huge), 1)
        self.assertEqual(len(huge[0].files), 1, "超大文件应单独成批")

    def test_empty_and_single_file_list(self) -> None:
        empty = plan_batches([], BatchPolicy())
        self.assertEqual(empty.total_files, 0)
        self.assertEqual(empty.total_batches, 0)
        self.assertEqual(empty.waves, 0)
        single = plan_batches([FileItem("src/only.vue", size=10)], BatchPolicy())
        self.assertEqual(single.total_batches, 1)
        self.assertEqual(single.waves, 1)
        self.assertEqual([f.path for f in single.batches[0].files], ["src/only.vue"])

    def test_dependency_cycle_rejected(self) -> None:
        items = [FileItem("a.js", deps=["b.js"]), FileItem("b.js", deps=["a.js"])]
        with self.assertRaises(ValueError):
            plan_batches(items, BatchPolicy())

    def test_unknown_dependency_ignored(self) -> None:
        items = [FileItem("a.js", deps=["not/in/list.js"])]
        plan = plan_batches(items, BatchPolicy())
        self.assertEqual(plan.waves, 1)


# ---------------------------------------------------------------------------
# quality gate
# ---------------------------------------------------------------------------
class BatchGateTest(unittest.TestCase):
    def test_hard_fail_signals(self) -> None:
        result = evaluate_batch(ast_ok=False, diff_ok=True, llm_score=99)
        self.assertTrue(result["hard_fail"])
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["verdict"], "rework")
        self.assertTrue(result["reasons"])

    def test_pass_and_rework_scores(self) -> None:
        passed = evaluate_batch(ast_ok=True, diff_ok=True, llm_score=95)
        self.assertEqual(passed["verdict"], "pass")
        self.assertGreaterEqual(passed["score"], 85)
        # 100*.3 + 100*.2 + 40*.2 + 0*.3 = 58 → rework
        rework = evaluate_batch(ast_ok=True, diff_ok=True, scoped_tests_ok=False,
                                llm_score=0)
        self.assertEqual(rework["verdict"], "rework")
        self.assertLess(rework["score"], 70)

    def test_truncated_forces_split_verdict(self) -> None:
        result = evaluate_batch(ast_ok=True, diff_ok=True, llm_score=95, truncated=True)
        self.assertEqual(result["verdict"], "rework")
        self.assertTrue(result["truncated"])

    def test_aggregate_gate(self) -> None:
        ok = aggregate_gate(batch_scores=[88, 91], coverage=1.0,
                            full_build_ok=True, browser_ok=True)
        self.assertEqual(ok["verdict"], "pass")
        self.assertEqual(ok["coverage"], 1.0)
        bad = aggregate_gate(batch_scores=[88, 91], coverage=0.5,
                             full_build_ok=False, browser_ok=True)
        self.assertEqual(bad["verdict"], "rework")
        self.assertTrue(any("覆盖率" in r for r in bad["reasons"]))
        self.assertTrue(any("构建" in r for r in bad["reasons"]))


# ---------------------------------------------------------------------------
# BatchStore / BatchQueue
# ---------------------------------------------------------------------------
class QueueTestBase(unittest.TestCase):
    def setUp(self) -> None:
        TMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=str(TMP_BASE)))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_queue(self, policy: BatchPolicy | None = None) -> BatchQueue:
        store = BatchStore(self.tmp / "batch.db")
        queue = BatchQueue(store, policy or BatchPolicy())
        self.addCleanup(store.close)
        return queue

    def make_group(self, paths: list, *, queue: BatchQueue, policy: BatchPolicy | None = None,
                   group_id: str = "g-test") -> str:
        policy = policy or queue.policy
        plan = plan_batches([FileItem(p, size=100) for p in paths], policy)
        return queue.create_group(plan=plan, run_id="run-1", node_id="transform",
                                  expert_id="code-transformer", group_id=group_id,
                                  policy=policy)


class ClaimLifecycleTest(QueueTestBase):
    def test_claim_is_atomic_and_serial(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=1))
        gid = self.make_group(["a.js", "b.js"], queue=queue)
        first = queue.claim_next(gid, "worker-1")
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.status, "running")
        self.assertIsNone(queue.claim_next(gid, "worker-2"), "同一时刻只能一个批次 running")
        self.assertTrue(queue.heartbeat(first.id, "worker-1"))
        self.assertFalse(queue.heartbeat(first.id, "worker-2"))

    def test_complete_promotes_next_batch(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=1))
        gid = self.make_group(["a.js", "b.js"], queue=queue)
        b1 = queue.claim_next(gid, "w")
        assert b1 is not None
        queue.ingest(b1.id, [{"path": "a.js", "status": "done"}])
        queue.complete(b1.id, score=90, verdict="pass")
        status = queue.status(gid)
        self.assertEqual(status["done_batches"], 1)
        b2 = queue.claim_next(gid, "w")
        self.assertIsNotNone(b2)
        assert b2 is not None
        self.assertNotEqual(b2.id, b1.id)
        queue.complete(b2.id, score=90)
        self.assertEqual(queue.status(gid)["done_batches"], 2)
        self.assertIsNone(queue.claim_next(gid, "w"))

    def test_wave_barrier_blocks_until_dependency_wave_done(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=1))
        items = [FileItem("a.js"), FileItem("b.js", deps=["a.js"])]
        plan = plan_batches(items, queue.policy)
        gid = queue.create_group(plan=plan, run_id="r", node_id="n", expert_id="e",
                                 group_id="g-wave", policy=queue.policy)
        self.assertEqual(plan.waves, 2)
        b1 = queue.claim_next(gid, "w")
        assert b1 is not None
        self.assertEqual([f["path"] for f in b1.files], ["a.js"])
        queue.complete(b1.id, score=90)
        b2 = queue.claim_next(gid, "w")
        self.assertIsNotNone(b2)
        assert b2 is not None
        self.assertEqual([f["path"] for f in b2.files], ["b.js"])

    def test_fail_retries_until_max_attempts_then_failed(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=1, max_attempts=2))
        gid = self.make_group(["a.js"], queue=queue)
        b = queue.claim_next(gid, "w")
        assert b is not None
        self.assertEqual(b.attempt, 1)
        self.assertEqual(queue.fail(b.id, "boom #1"), "ready")
        b = queue.claim_next(gid, "w")
        assert b is not None
        self.assertEqual(b.attempt, 2)
        self.assertEqual(queue.fail(b.id, "boom #2"), "failed")
        status = queue.status(gid)
        self.assertIn(b.id, status["failed"])
        self.assertEqual(status["done_batches"], 0)
        self.assertIsNone(queue.claim_next(gid, "w"), "failed 批次不再被认领")

    def test_claim_reclaims_expired_lease(self) -> None:
        """worker 崩溃后租约过期，批次应可被重新认领（否则组永久卡死）。"""
        queue = self.make_queue()
        gid = self.make_group(["a.js"], queue=queue)
        # store 级直接认领，用短 TTL 模拟 worker 崩溃后租约过期
        first = queue.store.claim_next(gid, "dead-worker", ttl_seconds=1)
        self.assertIsNotNone(first)
        time.sleep(2.1)  # 租约按秒取整，确保 now > lease_expires_at
        reclaimed = queue.store.claim_next(gid, "fresh-worker", ttl_seconds=1)
        self.assertIsNotNone(reclaimed, "租约已过期但 claim_next 仍返回 None（组永久卡死）")
        assert reclaimed is not None
        self.assertEqual(reclaimed.id, first.id)


class IngestApplyTest(QueueTestBase):
    def _setup_project(self) -> tuple:
        project = self.tmp / "project"
        staging = self.tmp / "staging"
        backup = self.tmp / "backup"
        (project / "src").mkdir(parents=True)
        (staging / "src").mkdir(parents=True)
        (project / "src" / "a.vue").write_text("OLD-A", encoding="utf-8")
        (project / "src" / "b.vue").write_text("OLD-B", encoding="utf-8")
        (staging / "src" / "a.vue").write_text("NEW-A", encoding="utf-8")
        (staging / "src" / "b.vue").write_text("NEW-B", encoding="utf-8")
        return project, staging, backup

    def test_ingest_reports_failed_and_missing(self) -> None:
        queue = self.make_queue()
        gid = self.make_group(["a.js", "b.js", "c.js"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        result = queue.ingest(batch.id, [
            {"path": "a.js", "status": "failed", "error": "parse"},
            {"path": "b.js", "status": "done", "staged_path": "stg/b.js"},
        ], attempt_id="1")
        self.assertEqual(result["failed"], ["a.js"])
        self.assertEqual(result["missing"], ["c.js"])
        self.assertEqual(result["ingested"], 2)
        items = {i.file_path: i for i in queue.store.list_items(batch.id)}
        self.assertEqual(items["a.js"].status, "failed")
        self.assertEqual(items["b.js"].status, "staged")
        self.assertEqual(items["b.js"].staged_path, "stg/b.js")
        self.assertEqual(items["c.js"].status, "pending")

    def test_apply_stages_to_workspace_with_backup_and_hash(self) -> None:
        project, staging, backup = self._setup_project()
        queue = self.make_queue(BatchPolicy(max_files_per_batch=5))
        gid = self.make_group(["src/a.vue", "src/b.vue"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        queue.ingest(batch.id, [
            {"path": "src/a.vue", "status": "done"},
            {"path": "src/b.vue", "status": "done"},
        ], staging_root=str(staging), project_root=str(project))

        result = queue.apply(batch.id, project_root=str(project),
                             staging_root=str(staging), backup_root=str(backup))
        self.assertEqual(sorted(result["applied"]), ["src/a.vue", "src/b.vue"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["errors"], [])
        self.assertEqual((project / "src" / "a.vue").read_text(encoding="utf-8"), "NEW-A")
        self.assertEqual((project / "src" / "b.vue").read_text(encoding="utf-8"), "NEW-B")
        self.assertEqual((backup / "src" / "a.vue").read_text(encoding="utf-8"), "OLD-A")
        items = {i.file_path: i for i in queue.store.list_items(batch.id)}
        self.assertEqual(items["src/a.vue"].status, "applied")
        self.assertEqual(items["src/a.vue"].applied_hash, _sha256("NEW-A"))
        self.assertEqual(items["src/b.vue"].applied_hash, _sha256("NEW-B"))

    def test_apply_is_idempotent(self) -> None:
        project, staging, backup = self._setup_project()
        queue = self.make_queue()
        gid = self.make_group(["src/a.vue", "src/b.vue"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        queue.ingest(batch.id, [{"path": "src/a.vue", "status": "done"},
                                {"path": "src/b.vue", "status": "done"}],
                     staging_root=str(staging), project_root=str(project))
        first = queue.apply(batch.id, project_root=str(project),
                            staging_root=str(staging), backup_root=str(backup))
        hashes_first = {i.file_path: i.applied_hash
                        for i in queue.store.list_items(batch.id)}
        second = queue.apply(batch.id, project_root=str(project),
                             staging_root=str(staging), backup_root=str(backup))
        self.assertEqual(second["errors"], [])
        self.assertEqual(second["applied"], first["applied"])
        hashes_second = {i.file_path: i.applied_hash
                         for i in queue.store.list_items(batch.id)}
        self.assertEqual(hashes_first, hashes_second, "重复 apply 后 applied_hash 必须一致")
        self.assertEqual((project / "src" / "a.vue").read_text(encoding="utf-8"), "NEW-A")

    def test_apply_reports_missing_staged_file(self) -> None:
        project, staging, backup = self._setup_project()
        queue = self.make_queue()
        gid = self.make_group(["src/a.vue", "src/b.vue"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        (staging / "src" / "b.vue").unlink()
        result = queue.apply(batch.id, project_root=str(project),
                             staging_root=str(staging), backup_root=str(backup))
        self.assertEqual(result["applied"], ["src/a.vue"])
        self.assertEqual(result["missing"], ["src/b.vue"])
        self.assertEqual(result["errors"], [])


class SplitRepairTest(QueueTestBase):
    def test_split_bisects_batch_and_moves_items(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=4))
        gid = self.make_group(["f0.js", "f1.js", "f2.js", "f3.js"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        ids = queue.split(batch.id)
        self.assertEqual(len(ids), 2)
        batches = {b.id: b for b in queue.store.list_batches(gid)}
        self.assertEqual(batches[batch.id].status, "split")
        for bid in ids:
            child = batches[bid]
            self.assertEqual(child.split_depth, 1)
            self.assertEqual(len(child.files), 2)
            self.assertTrue(child.status in ("ready", "running", "done"))
            # 文件 item 已迁移到子批，且仍是 pending
            items = queue.store.list_items(bid)
            self.assertEqual(len(items), 2)
            self.assertTrue(all(i.status == "pending" for i in items))
        self.assertEqual(queue.store.list_items(batch.id), [])

    def test_split_single_file_returns_empty(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=1))
        gid = self.make_group(["only.js"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        self.assertEqual(queue.split(batch.id), [])
        self.assertEqual(queue.store.get_batch(batch.id).status, "running")  # type: ignore[union-attr]

    def test_split_respects_max_split_depth(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=4, max_split_depth=0))
        gid = self.make_group(["f0.js", "f1.js", "f2.js", "f3.js"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        self.assertEqual(queue.split(batch.id), [], "max_split_depth=0 时不允许再拆")

    def test_repair_contains_only_failed_files(self) -> None:
        queue = self.make_queue(BatchPolicy(max_files_per_batch=4))
        gid = self.make_group(["a.js", "b.js", "c.js"], queue=queue)
        batch = queue.claim_next(gid, "w")
        assert batch is not None
        failed = ["a.js", "c.js"]
        rid = queue.repair(batch.id, failed)
        self.assertIsNotNone(rid)
        assert rid is not None
        repair = queue.store.get_batch(rid)
        self.assertIsNotNone(repair)
        assert repair is not None
        self.assertEqual([f["path"] for f in repair.files], failed)
        self.assertEqual(repair.status, "ready")
        self.assertEqual(repair.wave, batch.wave)
        self.assertIsNone(queue.repair(batch.id, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
