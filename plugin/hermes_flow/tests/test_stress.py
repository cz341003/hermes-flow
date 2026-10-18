"""R8 压力/故障注入：1000 文件规划、100 批 + 10 次瞬时故障。"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches
from flow_core.batch.driver import BatchAutoDriver


class StressLauncher:
    """注入 10 次瞬时失败；其余批次成功。"""

    def __init__(self, fail_first=10):
        self.fail_first = fail_first
        self.failed = set()
        self.launched = 0

    def launch(self, *, goal, context, metadata, correlation_id):
        self.launched += 1
        payload = json.loads(context)
        bid = metadata.get("batch_id") or correlation_id
        files = payload.get("files", [])
        for f in files:
            sp = Path(f["staging_path"])
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text("<template>v3</template>", encoding="utf-8")
        if bid not in self.failed and len(self.failed) < self.fail_first:
            self.failed.add(bid)
            return {"subagent_id": f"sa-{self.launched}", "_state": "FAILED",
                    "_error": "transient injected failure"}
        summary = json.dumps({"files": [{"path": f["path"], "status": "done"} for f in files],
                              "score": 92, "truncated": False})
        return {"subagent_id": f"sa-{self.launched}", "_summary": summary}

    def wait(self, handle, *, timeout):
        return {"completed": True, "timed_out": False,
                "state": handle.get("_state", "SUCCEEDED")}

    def result(self, handle):
        return {"terminal_state": handle.get("_state", "SUCCEEDED"),
                "summary": handle.get("_summary"),
                "error_message": handle.get("_error"),
                "error_classification": None}

    def cancel(self, handle, *, reason):
        return True


class StressTest(unittest.TestCase):
    def test_1000_file_plan(self):
        items = [FileItem(path=f"src/C{i:04d}.vue", size=1200,
                          deps=([f"src/C{i - 1:04d}.vue"] if i % 50 else []))
                 for i in range(1000)]
        plan = plan_batches(items, BatchPolicy(max_files_per_batch=7,
                                               context_budget_chars=28000))
        covered = sum(len(b.files) for b in plan.batches)
        self.assertEqual(covered, 1000)
        self.assertGreaterEqual(len(plan.batches), 100)
        waves = {b.wave for b in plan.batches}
        self.assertGreaterEqual(len(waves), 2)

    def test_100_batches_with_10_injected_failures(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        work = Path(tmp) / "work"
        (work / "src").mkdir(parents=True)
        store = BatchStore(os.path.join(tmp, "stress.db"))
        q = BatchQueue(store)
        files = [FileItem(path=f"src/S{i:04d}.vue", size=100) for i in range(700)]
        policy = BatchPolicy(max_files_per_batch=7, max_attempts=3, max_split_depth=0)
        plan = plan_batches(files, policy)
        gid = q.create_group(plan=plan, run_id="r-stress", node_id="transform",
                             expert_id="code-transformer", policy=policy)
        launcher = StressLauncher(fail_first=10)
        driver = BatchAutoDriver(q, launcher, staging_base=Path(tmp) / "staging",
                                 project_root=str(work), lock_dir=Path(tmp) / "locks",
                                 audit=False)
        started = time.time()
        out = driver.drive(gid, max_batches=200, max_seconds=300)
        elapsed = time.time() - started
        status = q.status(gid)
        self.assertTrue(out.done, out.to_dict())
        self.assertEqual(status["total_batches"], 100)
        self.assertEqual(status["done_batches"], 100)
        self.assertEqual(status["failed"], [])
        self.assertEqual(len(launcher.failed), 10)
        self.assertGreater(launcher.launched, 100)  # 10 次重试
        self.assertEqual(len(list((work / "src").glob("*.vue"))), 700)
        self.assertLess(elapsed, 120, f"100 batches took {elapsed:.1f}s")
        store.close()


if __name__ == "__main__":
    unittest.main()
