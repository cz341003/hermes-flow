"""质量门控单测：评分模型 + 门判定 + 回环计数。"""
import unittest

from vue3migrate_core.engine import Edge, ExecutionResult, Node, Scheduler, Workflow
from vue3migrate_core.quality import (
    GateTracker,
    QualityGate,
    SignalResult,
    Verdict,
    compute_score,
    gated_runner,
)


def full_pass():
    return [SignalResult(k, 1.0) for k in
            ["ast", "build", "types", "browser", "behavior"]]


class TestScoring(unittest.TestCase):
    def test_all_pass_is_100(self):
        s = compute_score(full_pass())
        self.assertAlmostEqual(s.score, 100.0, places=6)
        self.assertEqual(set(s.passed),
                         {"ast", "build", "types", "browser", "behavior"})
        self.assertEqual(s.failed, [])
        self.assertEqual(s.partial, [])

    def test_build_fail_drops_25(self):
        signals = full_pass()
        signals[1] = SignalResult("build", 0.0, "vite build 失败")
        s = compute_score(signals)
        self.assertAlmostEqual(s.score, 75.0, places=6)
        self.assertIn("build", s.failed)

    def test_ast_and_types_fail(self):
        signals = [
            SignalResult("ast", 0.0),
            SignalResult("build", 1.0),
            SignalResult("types", 0.0),
            SignalResult("browser", 1.0),
            SignalResult("behavior", 1.0),
        ]
        s = compute_score(signals)
        # 100 - 20 - 15 = 65
        self.assertAlmostEqual(s.score, 65.0, places=6)

    def test_partial_behavior(self):
        signals = full_pass()
        signals[4] = SignalResult("behavior", 0.5)
        s = compute_score(signals)
        # 100 - 7.5 = 92.5
        self.assertAlmostEqual(s.score, 92.5, places=6)
        self.assertIn("behavior", s.partial)

    def test_missing_signal_counts_as_fail(self):
        # 只给 ast，其余缺失 → 20 分
        s = compute_score([SignalResult("ast", 1.0)])
        self.assertAlmostEqual(s.score, 20.0, places=6)
        self.assertEqual(set(s.failed), {"build", "types", "browser", "behavior"})

    def test_dict_input(self):
        s = compute_score({
            "ast": True, "build": False, "types": True,
            "browser": 1, "behavior": 0.5,
        })
        # 20 + 0 + 15 + 25 + 7.5 = 67.5
        self.assertAlmostEqual(s.score, 67.5, places=6)

    def test_clamp_value(self):
        r = SignalResult("ast", 1.7)
        self.assertEqual(r.value, 1.0)
        r2 = SignalResult("ast", -0.3)
        self.assertEqual(r2.value, 0.0)


class TestGate(unittest.TestCase):
    def setUp(self):
        self.gate = QualityGate()

    def test_pass(self):
        d = self.gate.evaluate(90)
        self.assertIs(d.verdict, Verdict.PASS)
        self.assertEqual(d.loop_count, 0)

    def test_warn(self):
        d = self.gate.evaluate(80)
        self.assertIs(d.verdict, Verdict.WARN)
        self.assertEqual(len(d.warnings), 1)

    def test_rework_below_warn(self):
        d = self.gate.evaluate(60, loop_count=0)
        self.assertIs(d.verdict, Verdict.REWORK)

    def test_manual_after_max_loops(self):
        d = self.gate.evaluate(60, loop_count=3)
        self.assertIs(d.verdict, Verdict.MANUAL)

    def test_manual_boundary(self):
        # loop_count == max_loops(3) → MANUAL；2 → REWORK
        self.assertIs(self.gate.evaluate(60, 2).verdict, Verdict.REWORK)
        self.assertIs(self.gate.evaluate(60, 3).verdict, Verdict.MANUAL)

    def test_invalid_thresholds(self):
        with self.assertRaises(ValueError):
            QualityGate(pass_threshold=60, warn_threshold=70)
        with self.assertRaises(ValueError):
            QualityGate(max_loops=0)

    def test_boundary_values(self):
        self.assertIs(self.gate.evaluate(85).verdict, Verdict.PASS)
        self.assertIs(self.gate.evaluate(84.99).verdict, Verdict.WARN)
        self.assertIs(self.gate.evaluate(70).verdict, Verdict.WARN)
        self.assertIs(self.gate.evaluate(69.99).verdict, Verdict.REWORK)


class TestGateTracker(unittest.TestCase):
    def test_rework_increments_then_manual(self):
        t = GateTracker()
        subject = "transform:App.vue"
        self.assertIs(t.submit(subject, 60).verdict, Verdict.REWORK)
        self.assertEqual(t.loop_count(subject), 1)
        self.assertIs(t.submit(subject, 62).verdict, Verdict.REWORK)
        self.assertEqual(t.loop_count(subject), 2)
        self.assertIs(t.submit(subject, 65).verdict, Verdict.REWORK)
        self.assertEqual(t.loop_count(subject), 3)
        # 第 4 次 → MANUAL（达到 max_loops=3）
        self.assertIs(t.submit(subject, 66).verdict, Verdict.MANUAL)
        self.assertEqual(t.loop_count(subject), 3)

    def test_pass_resets_loop(self):
        t = GateTracker()
        subject = "transform:App.vue"
        t.submit(subject, 60)   # REWORK -> 1
        self.assertIs(t.submit(subject, 90).verdict, Verdict.PASS)
        self.assertEqual(t.loop_count(subject), 0)

    def test_warn_does_not_increment(self):
        t = GateTracker()
        subject = "transform:App.vue"
        self.assertIs(t.submit(subject, 80).verdict, Verdict.WARN)
        self.assertEqual(t.loop_count(subject), 0)


class TestGatedRunner(unittest.TestCase):
    @staticmethod
    def _single_node_wf():
        node = Node(id="transform", name="代码转化", phase="transform")
        return Workflow(id="wf", name="test", nodes=[node], edges=[])

    def test_low_score_loops_then_manual(self):
        wf = self._single_node_wf()
        sched = Scheduler(wf, max_attempts=3)
        # 恒定低分 60 → 回环 3 次后 FAILED（升级人工门）
        report = sched.run(gated_runner(
            lambda node, ctx: ExecutionResult(success=True, score=60)))
        self.assertFalse(report.done)
        self.assertEqual(report.failed_nodes, ["transform"])
        self.assertEqual(len(report.trace), 3)   # 执行了 3 轮

    def test_low_then_pass(self):
        wf = self._single_node_wf()
        sched = Scheduler(wf, max_attempts=3)
        scores = iter([60, 95])
        runner = gated_runner(
            lambda node, ctx: ExecutionResult(success=True, score=next(scores)))
        report = sched.run(runner)
        self.assertTrue(report.done)
        self.assertEqual(report.trace, ["transform", "transform"])  # 回环一次后通过

    def test_high_score_single_pass(self):
        wf = self._single_node_wf()
        sched = Scheduler(wf, max_attempts=3)
        report = sched.run(gated_runner(
            lambda node, ctx: ExecutionResult(success=True, score=90)))
        self.assertTrue(report.done)
        self.assertEqual(report.trace, ["transform"])

    def test_error_still_passthrough(self):
        wf = self._single_node_wf()
        sched = Scheduler(wf, max_attempts=3)
        report = sched.run(gated_runner(
            lambda node, ctx: ExecutionResult(success=False, error="转换抛异常")))
        self.assertFalse(report.done)
        self.assertEqual(report.failed_nodes, ["transform"])


if __name__ == "__main__":
    unittest.main()
