"""异常自愈单测：退避、异常分类、恢复策略、checkpoint 往返、自愈循环。"""
import os
import tempfile
import unittest

from vue3migrate_core.engine import Edge, ExecutionResult, Node, Scheduler, Workflow
from vue3migrate_core.recovery import (
    BackoffStrategy,
    FailureCategory,
    JsonCheckpointStore,
    RecoveryAction,
    RecoveryPolicy,
    autonomous_run,
    classify,
    restore_scheduler,
    snapshot_scheduler,
)


class TestBackoff(unittest.TestCase):
    def test_delay_sequence(self):
        b = BackoffStrategy(base_seconds=1.0, factor=2.0, jitter=0.0)
        self.assertEqual(b.delay(0), 1.0)
        self.assertEqual(b.delay(1), 2.0)
        self.assertEqual(b.delay(2), 4.0)
        self.assertEqual(b.delay(3), 8.0)

    def test_max_cap(self):
        b = BackoffStrategy(base_seconds=1.0, max_seconds=4.0,
                            factor=2.0, jitter=0.0)
        self.assertEqual(b.delay(10), 4.0)

    def test_jitter_range(self):
        b = BackoffStrategy(base_seconds=10.0, factor=1.0, jitter=0.2)
        for _ in range(50):
            d = b.delay(0)
            self.assertTrue(8.0 <= d <= 12.0)

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            BackoffStrategy(base_seconds=0)
        with self.assertRaises(ValueError):
            BackoffStrategy(max_seconds=0.5, base_seconds=1.0)
        with self.assertRaises(ValueError):
            BackoffStrategy(jitter=1.0)


class TestClassify(unittest.TestCase):
    def test_status_429(self):
        self.assertIs(classify("anything", status_code=429),
                      FailureCategory.RATE_LIMIT)

    def test_rate_limit_text(self):
        self.assertIs(classify("rate limit exceeded"), FailureCategory.RATE_LIMIT)
        self.assertIs(classify("请求被限流"), FailureCategory.RATE_LIMIT)

    def test_truncation(self):
        self.assertIs(classify("context length exceeded, truncated"),
                      FailureCategory.TRUNCATION)
        self.assertIs(classify("输出被截断"), FailureCategory.TRUNCATION)

    def test_timeout(self):
        self.assertIs(classify("request timed out"), FailureCategory.TIMEOUT)

    def test_dependency_missing(self):
        self.assertIs(classify("ModuleNotFoundError: No module named 'vuex'"),
                      FailureCategory.DEPENDENCY_MISSING)

    def test_compile_error(self):
        self.assertIs(classify("vite build failed: syntax error"),
                      FailureCategory.COMPILE_ERROR)

    def test_quality_low(self):
        self.assertIs(classify("评分低于阈值 70"), FailureCategory.QUALITY_LOW)

    def test_agent_drift(self):
        self.assertIs(classify("违规并行"), FailureCategory.AGENT_DRIFT)

    def test_destructive(self):
        self.assertIs(classify("destructive deploy action"),
                      FailureCategory.DESTRUCTIVE)

    def test_unknown(self):
        self.assertIs(classify("weird error"), FailureCategory.UNKNOWN)
        self.assertIs(classify(None), FailureCategory.UNKNOWN)


class TestPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = RecoveryPolicy(max_retries=3)

    def test_rate_limit_backoff(self):
        d = self.policy.decide(FailureCategory.RATE_LIMIT, 0, backoff_delay=2.0)
        self.assertIs(d.action, RecoveryAction.BACKOFF)
        self.assertEqual(d.delay_seconds, 2.0)

    def test_truncation_block(self):
        d = self.policy.decide(FailureCategory.TRUNCATION, 0)
        self.assertIs(d.action, RecoveryAction.BLOCK)

    def test_dependency_recover(self):
        d = self.policy.decide(FailureCategory.DEPENDENCY_MISSING, 0)
        self.assertIs(d.action, RecoveryAction.RECOVER_DEPENDENCY)

    def test_destructive_always_manual(self):
        d = self.policy.decide(FailureCategory.DESTRUCTIVE, 0)
        self.assertIs(d.action, RecoveryAction.MANUAL)

    def test_retry_limit_manual(self):
        d = self.policy.decide(FailureCategory.TIMEOUT, 3)
        self.assertIs(d.action, RecoveryAction.MANUAL)

    def test_retry_within_limit(self):
        d = self.policy.decide(FailureCategory.TIMEOUT, 2)
        self.assertIs(d.action, RecoveryAction.RETRY)


class TestCheckpoint(unittest.TestCase):
    def _wf(self):
        return Workflow(
            id="wf", name="t",
            nodes=[Node(id="a", name="A", phase="analyze"),
                   Node(id="b", name="B", phase="transform")],
            edges=[Edge("a", "b")],
        )

    def test_snapshot_roundtrip(self):
        sched = Scheduler(self._wf())
        sched.next()              # a -> running
        sched.complete("a")       # a -> done
        snap = snapshot_scheduler(sched)
        restored = restore_scheduler(snap)
        self.assertEqual(restored.states(), sched.states())
        self.assertEqual(restored.attempts("a"), sched.attempts("a"))
        # 续跑：b 仍可执行
        node = restored.next()
        self.assertEqual(node.id, "b")

    def test_json_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "checkpoint.json")
            store = JsonCheckpointStore(path)
            sched = Scheduler(self._wf())
            sched.next()
            sched.complete("a")
            store.save("wf", sched)
            loaded = store.load("wf")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.states()["a"], "done")
            self.assertEqual(loaded.states()["b"], "ready")
            # drop
            store.drop("wf")
            self.assertIsNone(store.load("wf"))

    def test_empty_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = JsonCheckpointStore(os.path.join(d, "nope.json"))
            self.assertIsNone(store.load("missing"))
            self.assertEqual(store.ids(), [])


class TestAutonomousRun(unittest.TestCase):
    def _wf(self):
        return Workflow(
            id="wf", name="t",
            nodes=[Node(id="a", name="A", phase="transform")],
            edges=[],
        )

    def test_rate_limit_backoff_then_success(self):
        sched = Scheduler(self._wf(), max_attempts=3)
        calls = {"n": 0}
        sleeps = []

        def runner(node, ctx):
            calls["n"] += 1
            if calls["n"] == 1:
                return ExecutionResult(success=False, error="429 rate limit")
            return ExecutionResult(success=True, score=90)

        report = autonomous_run(sched, runner,
                                sleep_fn=lambda s: sleeps.append(s))
        self.assertTrue(report.done)
        self.assertEqual(calls["n"], 2)          # 限流退避后重试成功
        self.assertEqual(len(sleeps), 1)         # 退避等待了一次
        self.assertEqual(report.events[0].action, "backoff")

    def test_truncation_blocks_and_checkpoints(self):
        with tempfile.TemporaryDirectory() as d:
            store = JsonCheckpointStore(os.path.join(d, "cp.json"))
            sched = Scheduler(self._wf(), max_attempts=3)
            runner = lambda node, ctx: ExecutionResult(  # noqa: E731
                success=True, truncated=True)
            report = autonomous_run(sched, runner, store=store,
                                    workflow_id="wf")
            self.assertFalse(report.done)
            self.assertEqual(report.states["a"], "blocked")
            self.assertEqual(report.events[0].action, "block")
            self.assertGreaterEqual(report.checkpointed, 1)
            # 快照已持久化，可从磁盘恢复 blocked 状态
            loaded = store.load("wf")
            self.assertEqual(loaded.states()["a"], "blocked")

    def test_timeout_retries_then_failed(self):
        sched = Scheduler(self._wf(), max_attempts=3)
        runner = lambda node, ctx: ExecutionResult(  # noqa: E731
            success=False, error="request timed out")
        report = autonomous_run(sched, runner)
        self.assertFalse(report.done)
        self.assertEqual(report.failed_nodes, ["a"])   # 重试 3 次后 FAILED
        self.assertIn(report.events[-1].action, ("retry", "manual"))

    def test_destructive_manual(self):
        sched = Scheduler(self._wf(), max_attempts=3)
        runner = lambda node, ctx: ExecutionResult(  # noqa: E731
            success=False, error="destructive deploy")
        report = autonomous_run(sched, runner)
        self.assertEqual(report.events[0].action, "manual")


if __name__ == "__main__":
    unittest.main()
