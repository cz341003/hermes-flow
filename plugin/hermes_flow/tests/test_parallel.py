"""R7 同 wave 并行 driver 单测：并发、worktree 隔离、稳定提交顺序。"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches
from flow_core.batch.driver import BatchAutoDriver


class ParallelLauncher:
    def __init__(self, work):
        self.work = Path(work)
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.contexts = []
        self.order = []

    def launch(self, *, goal, context, metadata, correlation_id):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.15)
            payload = json.loads(context)
            self.contexts.append(payload)
            files = payload.get("files", [])
            with self.lock:
                self.order.append(metadata.get("batch_id"))
            for f in files:
                sp = Path(f["staging_path"])
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text("<template>v3</template>", encoding="utf-8")
            summary = json.dumps({"files": [{"path": f["path"], "status": "done"} for f in files],
                                  "score": 92})
            return {"subagent_id": "sa-" + str(len(self.contexts)), "_summary": summary}
        finally:
            with self.lock:
                self.active -= 1

    def wait(self, handle, *, timeout):
        return {"completed": True, "timed_out": False, "state": "SUCCEEDED"}

    def result(self, handle):
        return {"terminal_state": "SUCCEEDED", "summary": handle.get("_summary"),
                "error_message": None, "error_classification": None}

    def cancel(self, handle, *, reason):
        return True


class ParallelDriverTest(unittest.TestCase):
    def test_parallelism_worktree_and_stable_commit_order(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        work = Path(tmp) / "work"
        (work / "src").mkdir(parents=True)
        for i in range(9):
            (work / "src" / f"P{i}.vue").write_text("<template>v2</template>", encoding="utf-8")
        store = BatchStore(os.path.join(tmp, "p.db"))
        q = BatchQueue(store)
        policy = BatchPolicy(max_files_per_batch=3, max_concurrent_batches=3,
                             max_attempts=2)
        plan = plan_batches([FileItem(path=f"src/P{i}.vue", size=100) for i in range(9)], policy)
        gid = q.create_group(plan=plan, run_id="r-par", node_id="transform",
                             expert_id="code-transformer", policy=policy)
        launcher = ParallelLauncher(work)
        driver = BatchAutoDriver(q, launcher, staging_base=Path(tmp) / "staging",
                                 project_root=str(work), lock_dir=Path(tmp) / "locks",
                                 worktree_base=Path(tmp) / "worktrees", audit=False,
                                 concurrency=3)
        out = driver.drive(gid, max_batches=3, max_seconds=30)
        self.assertTrue(out.done, out.to_dict())
        self.assertEqual(out.batches_done, 3)
        self.assertGreaterEqual(launcher.max_active, 2, "batches did not overlap")
        # worktree 隔离：子代理看到的是 worktrees 下的 source_path
        for ctx in launcher.contexts:
            for f in ctx.get("files", []):
                self.assertIn("worktrees", f["source_path"].replace("\\", "/"))
        # 稳定提交顺序：events 按 batch seq 升序
        ids = [e.batch_id for e in out.events if e.action == "done"]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(list((work / "src").glob("*.vue"))), 9)
        store.close()


if __name__ == "__main__":
    unittest.main()
