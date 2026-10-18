"""调度器单测：串行硬约束、违规并行拒绝、回环、切片上下文。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flow_core.engine import (  # noqa: E402
    Edge,
    ExecutionResult,
    Node,
    Scheduler,
    Workflow,
)


def ok():
    return ExecutionResult(success=True, score=90)


def err(msg="失败"):
    return ExecutionResult(success=False, error=msg)


def assert_topologically_ordered(testcase, wf, trace):
    """断言 trace 中每个节点都在其前驱之后出现。"""
    pos = {nid: i for i, nid in enumerate(trace)}
    for e in wf.edges:
        testcase.assertLess(pos[e.source], pos[e.target],
                            f"边 {e.source}->{e.target} 顺序被破坏: {trace}")


class TestSerialHardConstraint(unittest.TestCase):
    def _chain_wf(self):
        """A→B→C→D 纯链式，最严格的串行。"""
        nodes = [Node(id=x, name=x, phase="transform") for x in "ABCD"]
        edges = [Edge("A", "B"), Edge("B", "C"), Edge("C", "D")]
        return Workflow(id="chain", name="链式", nodes=nodes, edges=edges)

    def test_run_strict_serial_order(self):
        wf = self._chain_wf()
        s = Scheduler(wf)
        report = s.run(lambda node, ctx: ok())
        self.assertTrue(report.done)
        self.assertEqual(report.trace, ["A", "B", "C", "D"])
        assert_topologically_ordered(self, wf, report.trace)
        self.assertEqual(report.ticks, 4)

    def test_run_diamond_topological(self):
        nodes = [Node(id=x, name=x, phase="transform") for x in "ABCD"]
        edges = [Edge("A", "C"), Edge("B", "C"), Edge("C", "D")]
        wf = Workflow(id="diamond", name="菱形", nodes=nodes, edges=edges)
        s = Scheduler(wf)
        report = s.run(lambda node, ctx: ok())
        self.assertTrue(report.done)
        self.assertEqual(len(report.trace), 4)
        assert_topologically_ordered(self, wf, report.trace)

    def test_violating_parallel_rejected(self):
        """三个无依赖节点（都 ready），串行下 next() 只放行一个。"""
        nodes = [Node(id=x, name=x, phase="transform") for x in "ABC"]
        wf = Workflow(id="indep", name="独立", nodes=nodes, edges=[])
        s = Scheduler(wf)
        first = s.next()
        self.assertIsNotNone(first)
        # 第一个节点仍在 running，违规并行应被拒绝
        self.assertIsNone(s.next(), "串行下不应放行第二个节点")
        self.assertEqual(len(s.running_nodes()), 1)
        # 完成后才能继续
        s.complete(first.id)
        second = s.next()
        self.assertIsNotNone(second)
        self.assertNotEqual(second.id, first.id)

    def test_parallel_flag_allows_concurrency(self):
        nodes = [Node(id="A", name="A", phase="transform", parallel=True),
                 Node(id="B", name="B", phase="transform", parallel=True)]
        wf = Workflow(id="par", name="并行", nodes=nodes, edges=[])
        s = Scheduler(wf)
        a = s.next()
        self.assertEqual(a.id, "A")
        b = s.next()
        self.assertEqual(b.id, "B")  # 两者都 parallel，允许并发
        self.assertEqual(len(s.running_nodes()), 2)

    def test_non_parallel_blocks_parallel(self):
        """非 parallel 节点运行时，parallel 节点也不得放行。"""
        nodes = [Node(id="A", name="A", phase="transform", parallel=False),
                 Node(id="B", name="B", phase="transform", parallel=True)]
        wf = Workflow(id="mix", name="混合", nodes=nodes, edges=[])
        s = Scheduler(wf)
        s.next()  # A (非 parallel)
        self.assertIsNone(s.next(), "非 parallel 节点独占，parallel 也不得并发")


class TestRetryLoop(unittest.TestCase):
    def test_failed_retry_then_give_up(self):
        nodes = [Node(id="A", name="A", phase="transform")]
        wf = Workflow(id="w", name="重试", nodes=nodes, edges=[])
        s = Scheduler(wf, max_attempts=3)
        report = s.run(lambda node, ctx: err("编译失败"))
        self.assertFalse(report.done)
        self.assertEqual(report.failed_nodes, ["A"])
        # trace 记录 3 次尝试（每次 tick 尝试一次）
        self.assertEqual(report.trace.count("A"), 3)

    def test_failed_then_success(self):
        nodes = [Node(id="A", name="A", phase="transform")]
        wf = Workflow(id="w", name="重试成功", nodes=nodes, edges=[])
        s = Scheduler(wf, max_attempts=3)
        counter = {"n": 0}

        def flaky(node, ctx):
            counter["n"] += 1
            return ok() if counter["n"] >= 2 else err()

        report = s.run(flaky)
        self.assertTrue(report.done)
        self.assertEqual(report.trace, ["A", "A"])  # 第一次失败回 ready，第二次成功


class TestBlockedAndSlice(unittest.TestCase):
    def test_blocked_causes_stuck(self):
        nodes = [Node(id="A", name="A", phase="transform")]
        wf = Workflow(id="w", name="阻塞", nodes=nodes, edges=[])
        s = Scheduler(wf)
        truncated = ExecutionResult(success=False, truncated=True)
        report = s.run(lambda node, ctx: truncated)
        self.assertFalse(report.done)
        self.assertTrue(s.is_stuck())
        # unblock 后恢复可继续
        s.unblock("A")
        self.assertFalse(s.is_stuck())

    def test_slice_context_only_current(self):
        """切片上下文只含当前节点 + 依赖摘要，不含历史全量。"""
        nodes = [Node(id=x, name=x, phase="transform") for x in "ABC"]
        edges = [Edge("A", "C"), Edge("B", "C")]
        wf = Workflow(id="w", name="切片", nodes=nodes, edges=edges)
        s = Scheduler(wf)
        node = s.next()  # A
        sl = s.build_slice(node)
        self.assertEqual(sl["node"]["id"], "A")
        self.assertEqual(sl["dependencies_done"], [])
        self.assertNotIn("trace", sl)
        self.assertNotIn("history", sl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
