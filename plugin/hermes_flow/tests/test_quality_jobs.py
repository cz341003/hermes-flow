"""异步质量 job 管理器单测。"""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.quality.jobs import QualityJobManager  # noqa: E402


class QualityJobsTest(unittest.TestCase):
    def test_done_and_error(self):
        mgr = QualityJobManager()
        done = mgr.submit(lambda **kw: {"build": {"ok": True}, **kw}, project_root="x")
        err = mgr.submit(lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        deadline = time.time() + 5
        while time.time() < deadline:
            d = mgr.get(done["id"])
            e = mgr.get(err["id"])
            if d["status"] != "running" and e["status"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(mgr.get(done["id"])["status"], "done")
        self.assertTrue(mgr.get(done["id"])["result"]["build"]["ok"])
        self.assertEqual(mgr.get(err["id"])["status"], "error")
        self.assertIn("boom", mgr.get(err["id"])["error"])
        self.assertEqual(len(mgr.list()), 2)

    def test_cleanup_and_unknown(self):
        mgr = QualityJobManager(retention_seconds=0.01)
        job = mgr.submit(lambda: 1)
        time.sleep(0.1)
        # 新提交触发清理
        mgr.submit(lambda: 2)
        self.assertIsNone(mgr.get(job["id"]))
        self.assertIsNone(mgr.get("missing"))


if __name__ == "__main__":
    unittest.main()
