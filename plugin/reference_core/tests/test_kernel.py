"""状态内核单测：覆盖 M1 验收标准（状态机迁移 + checkpoint 重启恢复回放）。

运行方式（零第三方依赖，仅标准库 unittest）：
    python -m unittest discover -s tests -v
或单文件：
    python -m unittest tests.test_kernel -v
"""
import os
import sys
import tempfile
import unittest

# 将容器目录加入 sys.path，使 `import vue3migrate_core` 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vue3migrate_core.kernel import (  # noqa: E402
    Kernel,
    InvalidTransition,
    GoalStatus,
    TodoStatus,
    Phase,
    GateKind,
    GateStatus,
)


class KernelTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "kernel_test.db")
        self.k = Kernel(self.db_path)

    def tearDown(self):
        self.k.close()
        self._tmp.cleanup()

    def _make_goal(self, quota_total=0):
        return self.k.create_goal("迁移样例项目", quota_total=quota_total)


class TestGoalAndTodo(KernelTestCase):
    def test_goal_create_and_list(self):
        g = self._make_goal()
        self.assertEqual(g.status, GoalStatus.PLANNING)
        got = self.k.store.get_goal(g.id)
        self.assertEqual(got.title, "迁移样例项目")
        self.assertEqual(len(self.k.store.list_goals()), 1)

    def test_todo_dependencies_serialized(self):
        g = self._make_goal()
        a = self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        b = self.k.create_todo(g.id, "b.vue", Phase.TRANSFORM, dependencies=[a.id])
        got = self.k.store.get_todo(b.id)
        self.assertEqual(got.dependencies, [a.id])


class TestClaimAtomic(KernelTestCase):
    def test_claim_success_and_duplicate_fail(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        self.assertEqual(self.k.claim(g.id, "agent-1"), self.k.store.get_todo(t.id))
        # 重复认领应失败（已被认领）
        self.assertIsNone(self.k.claim(g.id, "agent-2", todo_id=t.id))
        got = self.k.store.get_todo(t.id)
        self.assertEqual(got.status, TodoStatus.CLAIMED)
        self.assertEqual(got.owner_agent, "agent-1")
        self.assertIsNotNone(got.lease_expires_at)

    def test_claim_respects_dependencies(self):
        g = self._make_goal()
        a = self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        b = self.k.create_todo(g.id, "b.vue", Phase.TRANSFORM, dependencies=[a.id])
        # b 依赖 a，a 未完成，claim_next 应只给 a
        claimed = self.k.claim(g.id, "agent-1")
        self.assertEqual(claimed.id, a.id)
        self.assertIsNone(self.k.claim(g.id, "agent-2"))  # 只剩 b 且依赖未满足


class TestStateMachine(KernelTestCase):
    def test_illegal_transition_rejected(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        # ready -> done 是非法迁移（必须先 claim）
        with self.assertRaises(InvalidTransition):
            self.k.update(t.id, TodoStatus.DONE)

    def test_failed_retry_loop_then_give_up(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.TRANSFORM, max_attempts=3)
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        # 第 1 次失败 -> 回 ready（attempts=1）
        u = self.k.update(t.id, TodoStatus.FAILED, error="编译失败")
        self.assertEqual(u.status, TodoStatus.READY)
        self.assertEqual(u.attempts, 1)
        # 第 2 次失败 -> 回 ready（attempts=2）
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        u = self.k.update(t.id, TodoStatus.FAILED, error="仍失败")
        self.assertEqual(u.status, TodoStatus.READY)
        self.assertEqual(u.attempts, 2)
        # 第 3 次失败 -> 达到上限，保持 failed
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        u = self.k.update(t.id, TodoStatus.FAILED, error="最终失败")
        self.assertEqual(u.status, TodoStatus.FAILED)
        self.assertEqual(u.attempts, 3)

    def test_blocked_transition_allowed(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.TRANSFORM)
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        # claimed -> blocked（限流/截断）
        u = self.k.update(t.id, TodoStatus.BLOCKED, error="429 限流")
        self.assertEqual(u.status, TodoStatus.BLOCKED)


class TestShouldRun(KernelTestCase):
    def test_should_run_ready(self):
        g = self._make_goal()
        self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        self.assertTrue(self.k.should_run(g.id).should)

    def test_should_run_no_ready_after_claim(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        self.assertFalse(self.k.should_run(g.id).should)

    def test_should_run_quota_exhausted(self):
        g = self._make_goal(quota_total=1)
        self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        self.assertTrue(self.k.spend_slot(g.id))
        self.assertFalse(self.k.should_run(g.id).should)

    def test_should_run_terminal_and_gate(self):
        g = self._make_goal()
        self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        self.k.store.set_goal_status(g.id, GoalStatus.DONE)
        self.assertFalse(self.k.should_run(g.id).should)
        self.k.store.set_goal_status(g.id, GoalStatus.WAITING_GATE)
        self.assertFalse(self.k.should_run(g.id).should)


class TestSpendSlot(KernelTestCase):
    def test_quota_enforced(self):
        g = self._make_goal(quota_total=2)
        self.assertTrue(self.k.spend_slot(g.id))
        self.assertTrue(self.k.spend_slot(g.id))
        self.assertFalse(self.k.spend_slot(g.id))  # 超限
        got = self.k.store.get_goal(g.id)
        self.assertEqual(got.quota_used, 2)

    def test_unlimited_quota(self):
        g = self._make_goal(quota_total=0)
        self.assertTrue(self.k.spend_slot(g.id))
        self.assertTrue(self.k.spend_slot(g.id, 100))


class TestGoalAdvance(KernelTestCase):
    def test_goal_auto_done(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.TRANSFORM)
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        self.k.update(t.id, TodoStatus.DONE, score=90)
        self.assertEqual(self.k.store.get_goal(g.id).status, GoalStatus.DONE)

    def test_goal_waiting_gate(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.TRANSFORM)
        self.k.store.create_gate(g.id, GateKind.HUMAN, question="请确认发布")
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        self.k.update(t.id, TodoStatus.DONE, score=90)
        self.assertEqual(self.k.store.get_goal(g.id).status, GoalStatus.WAITING_GATE)


class TestEvidenceAndExperience(KernelTestCase):
    def test_evidence_recorded(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.TRANSFORM)
        self.k.claim(g.id, "agent-1", todo_id=t.id)
        self.k.update(t.id, TodoStatus.DONE, agent_id="agent-1", score=88,
                      artifacts=["diff/a.patch"], notes="转化完成")
        evs = self.k.store.list_evidence(t.id)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].score, 88)
        self.assertEqual(evs[0].artifacts, ["diff/a.patch"])

    def test_experience_hit_and_search(self):
        self.k.add_experience("transform", "Options API 转 setup 时丢失 this 上下文",
                              "统一用 useXxx composable 提取", versions="vue3.4")
        hits = self.k.store.search_experience(category="transform")
        self.assertEqual(len(hits), 1)
        self.k.hit_experience(hits[0].id)
        self.assertEqual(self.k.store.search_experience(category="transform")[0].times_hit, 2)


class TestRefreshState(KernelTestCase):
    def test_snapshot_content(self):
        g = self._make_goal()
        a = self.k.create_todo(g.id, "a.vue", Phase.ANALYZE)
        self.k.create_todo(g.id, "b.vue", Phase.TRANSFORM, dependencies=[a.id])
        snap = self.k.refresh_state(g.id)
        self.assertEqual(snap.goal.id, g.id)
        self.assertEqual(snap.progress["total"], 2)
        self.assertEqual(snap.progress["done"], 0)
        self.assertIsNotNone(snap.next_todo)
        self.assertEqual(snap.next_todo.id, a.id)


class TestCheckpointPersistence(KernelTestCase):
    def test_restore_across_reopen(self):
        g = self._make_goal()
        t = self.k.create_todo(g.id, "a.vue", Phase.TRANSFORM)
        self.k.checkpoint(g.id, t.id, {"cursor": 12, "partial": "xxx"})
        # 关闭内核（模拟进程退出）
        self.k.close()
        # 重新打开同一 db（模拟重启）
        k2 = Kernel(self.db_path)
        try:
            state = k2.restore_from_checkpoint(g.id)
            self.assertIsNotNone(state)
            self.assertEqual(state["cursor"], 12)
            self.assertEqual(state["partial"], "xxx")
            # goal/todo 状态仍持久存在
            self.assertEqual(k2.store.get_goal(g.id).title, "迁移样例项目")
            self.assertEqual(k2.store.get_todo(t.id).file_path, "a.vue")
        finally:
            k2.close()


class TestStateMachinePure(unittest.TestCase):
    def test_transition_matrix(self):
        from vue3migrate_core.kernel.state_machine import (
            can_transition, TODO_TRANSITIONS, GOAL_TRANSITIONS,
        )
        self.assertTrue(can_transition(TodoStatus.READY, TodoStatus.CLAIMED, TODO_TRANSITIONS))
        self.assertFalse(can_transition(TodoStatus.READY, TodoStatus.DONE, TODO_TRANSITIONS))
        self.assertTrue(can_transition(GoalStatus.RUNNING, GoalStatus.DONE, GOAL_TRANSITIONS))
        self.assertFalse(can_transition(GoalStatus.DONE, GoalStatus.RUNNING, GOAL_TRANSITIONS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
