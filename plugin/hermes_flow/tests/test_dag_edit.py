"""DAG 编辑：节点 meta.x/y 保存/回读，环仍被拒绝。"""
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


class DagEditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        self.rt = FlowRuntime(ROOT, Path(self.tmp) / "data")

    def test_positions_roundtrip(self):
        wf = self.rt.registry.get_workflow("vue3-migrate-6phase")
        data = wf.definition
        data["nodes"][0].setdefault("meta", {})["x"] = 42
        data["nodes"][0]["meta"]["y"] = 77
        self.rt.registry.save_workflow(data)
        again = self.rt.registry.get_workflow("vue3-migrate-6phase")
        node = again.definition["nodes"][0]
        self.assertEqual(node["meta"]["x"], 42)
        self.assertEqual(node["meta"]["y"], 77)

    def test_cycle_rejected(self):
        wf = self.rt.registry.get_workflow("vue3-migrate-6phase")
        data = wf.definition
        a, b = data["nodes"][0]["id"], data["nodes"][1]["id"]
        data["edges"] = data["edges"] + [
            {"source": a, "target": b}, {"source": b, "target": a}]
        with self.assertRaises(ValueError):
            self.rt.registry.save_workflow(data)


if __name__ == "__main__":
    unittest.main()
