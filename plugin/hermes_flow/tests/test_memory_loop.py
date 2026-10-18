"""R6 记忆闭环：pre_llm_call 自动召回 + 批次失败自动沉淀。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
os.environ.setdefault("HERMES_HOME", tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir()))

import hermes_flow  # noqa: E402
from hermes_flow.runtime import FlowRuntime  # noqa: E402

PLUGIN_ROOT = ROOT


class MemoryLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        self.rt = FlowRuntime(PLUGIN_ROOT, Path(self.tmp) / "data")
        self.rt.experience_add(category="antdv", trigger="scopedSlots",
                               solution="Ant Design Vue 4 使用 #default 插槽替代 scopedSlots。")
        # 让插件级 get_runtime() 指向同一数据目录
        hermes_flow.configure(plugin_root=PLUGIN_ROOT, data_dir=Path(self.tmp) / "data")
        self.run = self.rt.start_run(workflow_id="vue3-migrate-6phase",
                                     project_root=self.tmp,
                                     files=[{"path": "src/A.vue", "size": 100}])
        self.rt.batch_plan(run_id=self.run["id"], node_id="transform")

    def test_pre_llm_call_injects_experience_and_progress(self):
        out = hermes_flow._pre_llm_call(user_message="scopedSlots 迁移报错", session_id="s1")
        self.assertIsInstance(out, dict)
        ctx = out["context"]
        self.assertIn("scopedSlots", ctx)
        self.assertIn("#default", ctx)
        self.assertIn(self.run["id"], ctx)
        self.assertLessEqual(len(ctx), 9000)

    def test_pre_llm_call_without_state(self):
        hermes_flow.configure(plugin_root=PLUGIN_ROOT, data_dir=Path(self.tmp) / "empty")
        self.assertIsNone(hermes_flow._pre_llm_call(user_message="nothing"))

    def test_distill_failure_actions(self):
        events = [
            {"action": "drift", "error": "FLOW_BATCH_WRITE_SCOPE: rogue.js"},
            {"action": "rate_limited", "error": "429 rate limit"},
            {"action": "split", "error": "output truncated"},
            {"action": "failed", "error": "child timeout"},
        ]
        count = self.rt.distill_batch_experiences(self.run["id"], "transform", events)
        self.assertGreaterEqual(count, 4)
        cats = {e["category"] for e in self.rt.experience_search(query="", limit=20)}
        self.assertIn("write_scope", cats)
        self.assertIn("rate_limit", cats)
        self.assertIn("truncation", cats)
        # 事件流有 memory_distilled
        evs = self.rt.run_events(self.run["id"])["events"]
        self.assertTrue(any(e["type"] == "memory_distilled" for e in evs))


if __name__ == "__main__":
    unittest.main()
