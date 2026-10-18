"""R9 LoopX 后端单测：工厂、Runtime backend、LoopXKernel 五原语、降级。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
os.environ.setdefault("HERMES_HOME", tempfile.mkdtemp(
    dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir()))

from hermes_flow.runtime import FlowRuntime  # noqa: E402
from hermes_flow.flow_core.adapters import LoopXKernel, create_kernel  # noqa: E402

PLUGIN_ROOT = ROOT


class LoopXBackendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        self.rt = FlowRuntime(PLUGIN_ROOT, Path(self.tmp) / "data", backend="loopx")

    def test_runtime_uses_loopx_kernel(self):
        self.assertEqual(self.rt.backend, "loopx")
        self.assertIsInstance(self.rt.kernel, LoopXKernel)
        info = self.rt.backend_info()
        self.assertEqual(info["backend"], "loopx")
        self.assertTrue(info["kernel_ok"])

    def test_loopx_kernel_goal_todo_roundtrip(self):
        k = self.rt.kernel
        goal = k.create_goal("迁移", workflow_id="vue3-migrate-6phase")
        todo = k.create_todo(goal.id, "src/A.vue", "transform")
        self.assertEqual(k.should_run(goal.id).should, True)
        claimed = k.claim(goal.id, "agent-1")
        self.assertEqual(claimed.id, todo.id)
        k.update(claimed.id, "done", agent_id="agent-1", score=95)
        self.assertTrue((Path(self.tmp) / "data" / "loopx" / ".loopx").is_dir())
        self.assertEqual(k.refresh_state(goal.id).progress["done"], 1)

    def test_backend_switch_and_persist(self):
        info = self.rt.set_backend("sqlite")
        self.assertEqual(info["backend"], "sqlite")
        cfg = json.loads((Path(self.tmp) / "data" / "backend.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["backend"], "sqlite")
        rt2 = FlowRuntime(PLUGIN_ROOT, Path(self.tmp) / "data")
        self.assertEqual(rt2.backend, "sqlite")

    def test_invalid_backend_falls_back(self):
        rt = FlowRuntime(PLUGIN_ROOT, Path(self.tmp) / "other", backend="nope")
        self.assertEqual(rt.backend, "sqlite")
        self.assertIn("unknown backend", rt.backend_error)
        self.assertEqual(type(rt.kernel).__name__, "Kernel")

    def test_factory(self):
        k = create_kernel("loopx", root=str(Path(self.tmp) / "factory"))
        self.assertIsInstance(k, LoopXKernel)


if __name__ == "__main__":
    unittest.main()
