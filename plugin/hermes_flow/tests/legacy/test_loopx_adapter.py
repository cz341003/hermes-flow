"""LoopX 适配器单测：内核工厂 + LoopXKernel 五原语 + 双后端语义一致。"""
import os
import tempfile
import unittest

from flow_core.adapters import LoopXKernel, create_kernel
from flow_core.kernel import Kernel, InvalidTransition
from flow_core.kernel.models import GoalStatus, TodoStatus
from flow_core.kernel.protocol import StateKernel


class TestCreateKernel(unittest.TestCase):
    def test_sqlite_backend(self):
        k = create_kernel("sqlite", db_path=":memory:")
        self.assertIsInstance(k, Kernel)
        self.assertIsInstance(k, StateKernel)
        k.close()

    def test_loopx_backend(self):
        with tempfile.TemporaryDirectory() as d:
            k = create_kernel("loopx", root=d)
            self.assertIsInstance(k, LoopXKernel)
            self.assertIsInstance(k, StateKernel)
            k.close()

    def test_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_kernel("nope")


class TestLoopXKernelPrimitives(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.k = LoopXKernel(self.root)

    def tearDown(self):
        self.k.close()
        self._tmp.cleanup()

    def _mk(self, deps=False):
        g = self.k.create_goal("迁移", quota_total=10)
        a = self.k.create_todo(g.id, "a.vue", "analyze")
        b = self.k.create_todo(g.id, "b.vue", "transform",
                               dependencies=[a.id] if deps else None)
        return g, a, b

    def test_should_run_and_claim(self):
        g, a, b = self._mk(deps=True)
        r = self.k.should_run(g.id)
        self.assertTrue(r.should)
        # 依赖未满足，只能认领 a
        claimed = self.k.claim(g.id, "agent-1")
        self.assertEqual(claimed.id, a.id)
        self.assertEqual(claimed.status, TodoStatus.CLAIMED)
        # a 未完成，b 依赖未满足，无法认领 b
        self.assertIsNone(self.k.claim(g.id, "agent-2", todo_id=b.id))

    def test_update_hard_constraint(self):
        g, a, _ = self._mk()
        self.k.claim(g.id, "agent-1", todo_id=a.id)
        # ready -> done 非法（需先 claim）
        g2, a2, _ = self._mk()
        with self.assertRaises(InvalidTransition):
            self.k.update(a2.id, TodoStatus.DONE)

    def test_complete_flow_advances_goal(self):
        g, a, b = self._mk(deps=True)
        self.k.claim(g.id, "a1", todo_id=a.id)
        self.k.update(a.id, TodoStatus.DONE)
        self.k.claim(g.id, "a2", todo_id=b.id)
        self.k.update(b.id, TodoStatus.DONE)
        goal = self.k._get_goal(g.id)
        self.assertEqual(goal.status, GoalStatus.DONE)

    def test_failed_retry_loop(self):
        g, a, _ = self._mk()
        self.k.claim(g.id, "a1", todo_id=a.id)
        self.k.update(a.id, TodoStatus.FAILED)
        # 未超 max_attempts=3，应自动回 ready
        t = self.k._get_todo(a.id)
        self.assertEqual(t.status, TodoStatus.READY)
        self.assertEqual(t.attempts, 1)

    def test_spend_slot_quota(self):
        g, a, _ = self._mk()
        goal = self.k._get_goal(g.id)
        self.assertEqual(goal.quota_total, 10)
        self.assertTrue(self.k.spend_slot(g.id, 3))
        self.assertEqual(self.k._get_goal(g.id).quota_used, 3)

    def test_checkpoint_roundtrip(self):
        g, a, _ = self._mk()
        self.k.checkpoint(g.id, a.id, {"cursor": 5, "trace": ["x"]})
        restored = self.k.restore_from_checkpoint(g.id)
        self.assertEqual(restored["cursor"], 5)
        self.assertEqual(restored["trace"], ["x"])

    def test_experience_dedup(self):
        e1 = self.k.add_experience("transform", "filters 被移除", "改用 computed")
        e2 = self.k.add_experience("transform", "filters 被移除", "改用 computed")
        self.assertEqual(e1.id, e2.id)
        self.assertEqual(e2.times_hit, 2)

    def test_persistence_across_reopen(self):
        g, a, b = self._mk(deps=True)
        self.k.claim(g.id, "a1", todo_id=a.id)
        self.k.update(a.id, TodoStatus.DONE)
        self.k.close()
        # 重新打开（模拟进程重启）
        k2 = LoopXKernel(self.root)
        t = k2._get_todo(a.id)
        self.assertEqual(t.status, TodoStatus.DONE)
        # b 依赖已满足，可认领
        claimed = k2.claim(g.id, "a2", todo_id=b.id)
        self.assertEqual(claimed.id, b.id)
        k2.close()


class TestParityWithSqlite(unittest.TestCase):
    """同一操作序列，SQLite 与 LoopX 后端结果一致。"""

    def test_same_outcome(self):
        with tempfile.TemporaryDirectory() as d:
            sqlite = Kernel(os.path.join(d, "s.db"))
            loopx = LoopXKernel(os.path.join(d, "lx"))
            for k in (sqlite, loopx):
                g = k.create_goal("迁移", quota_total=10)
                a = k.create_todo(g.id, "a.vue", "analyze")
                b = k.create_todo(g.id, "b.vue", "transform", dependencies=[a.id])
                self.assertEqual(k.should_run(g.id).should, True)
                c = k.claim(g.id, "agent-1")
                self.assertEqual(c.id, a.id)
                k.update(a.id, "done")
                c2 = k.claim(g.id, "agent-2")
                self.assertEqual(c2.id, b.id)
                k.update(b.id, "done")
                self.assertEqual(k.refresh_state(g.id).goal.status, "done")
                k.close()


if __name__ == "__main__":
    unittest.main()
