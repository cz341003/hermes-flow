"""R5b 事件流 / 人工门 / 节点重跑单测。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
os.environ.setdefault("HERMES_HOME", tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir()))

from hermes_flow.runtime import FlowRuntime  # noqa: E402

PLUGIN_ROOT = ROOT


class EventsGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        self.rt = FlowRuntime(PLUGIN_ROOT, Path(self.tmp) / "data")
        files = [{"path": f"src/C{i}.vue", "size": 100} for i in range(3)]
        self.run = self.rt.start_run(workflow_id="vue3-migrate-6phase",
                                     project_root=self.tmp, files=files)
        self.plan = self.rt.batch_plan(run_id=self.run["id"], node_id="transform")
        self.group = self.plan["group_id"]

    def test_event_replay_cursor(self):
        first = self.rt.run_events(self.run["id"], after=0)
        self.assertGreaterEqual(first["last_seq"], 2)
        self.assertEqual(first["events"][0]["type"], "created")
        seq = first["events"][1]["seq"]
        tail = self.rt.run_events(self.run["id"], after=seq)
        self.assertTrue(all(e["seq"] > seq for e in tail["events"]))
        self.assertEqual(tail["last_seq"], first["last_seq"])

    def test_gate_approve_and_reject(self):
        out = self.rt.gate_run(self.run["id"], "approve", "ok")
        self.assertEqual(out["status"], "running")
        events = self.rt.run_events(self.run["id"])["events"]
        self.assertEqual(events[-1]["type"], "gate_approve")
        out = self.rt.gate_run(self.run["id"], "reject", "no")
        self.assertEqual(out["status"], "cancelled")

    def test_rerun_failed_batch(self):
        batch = self.rt.queue.claim_next(self.group, "test")
        self.assertIsNotNone(batch)
        # max_attempts 默认 3；连续 fail 到 failed
        status = "ready"
        for _ in range(5):
            status = self.rt.queue.fail(batch.id, "test")
            if status == "failed":
                break
            batch = self.rt.queue.claim_next(self.group, "test")
            if batch is None:
                break
        if status != "failed":
            batch = self.rt.queue.claim_next(self.group, "test")
            self.rt.queue.fail(batch.id, "test")
        # 直接重跑节点
        before = self.rt.batch_status(self.group)
        self.assertTrue(before["failed"], before)
        out = self.rt.rerun_node(self.run["id"], "transform")
        self.assertGreaterEqual(out["retried"], 1)
        after = self.rt.batch_status(self.group)
        self.assertFalse(after["failed"])


if __name__ == "__main__":
    unittest.main()
