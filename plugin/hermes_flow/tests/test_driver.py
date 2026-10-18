"""R1 自动批次 driver 单测：成功、截断拆批、格式纠正、429、超时、单例锁。"""
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
from flow_core.batch.driver import BatchAutoDriver, FileLock, parse_child_summary


class FakeLauncher:
    def __init__(self, behaviors, project_root):
        self.behaviors = list(behaviors)
        self.project_root = project_root
        self.launched = []
        self.cancelled = []

    def launch(self, *, goal, context, metadata, correlation_id):
        self.launched.append({"goal": goal, "context": context, "metadata": metadata,
                              "correlation_id": correlation_id})
        behavior = self.behaviors.pop(0) if self.behaviors else "success"
        if behavior == "raise_parent":
            raise RuntimeError("No active Hermes parent session is available.")
        # 模拟子代理写 staging
        try:
            import re
            raw = context[context.find("{"):context.rfind("}") + 1]
            payload = json.loads(raw)
            for f in payload.get("files", []):
                sp = Path(f["staging_path"])
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text("<template>v3</template>", encoding="utf-8")
            expected = [f["path"] for f in payload.get("files", [])]
        except Exception:  # noqa: BLE001
            expected = []
        idx = len(self.launched)
        if behavior == "success":
            summary = json.dumps({"files": [{"path": p, "status": "done"} for p in expected],
                                  "score": 92, "truncated": False})
            return {"subagent_id": f"sa-{idx}", "_summary": summary}
        if behavior == "invalid":
            return {"subagent_id": f"sa-{idx}", "_summary": "这不是 JSON"}
        if behavior == "truncated":
            return {"subagent_id": f"sa-{idx}", "_state": "FAILED",
                    "_error": "output truncated at token limit"}
        if behavior == "rate_limit":
            return {"subagent_id": f"sa-{idx}", "_state": "FAILED",
                    "_error": "429 rate limit exceeded"}
        if behavior == "drift":
            (Path(self.project_root) / "outside.txt").write_text("drift", encoding="utf-8")
            summary = json.dumps({"files": [{"path": p, "status": "done"} for p in expected],
                                  "score": 92})
            return {"subagent_id": f"sa-{idx}", "_summary": summary}
        if behavior == "timeout":
            return {"subagent_id": f"sa-{idx}", "_state": "RUNNING", "_timeout": True}
        return {"subagent_id": f"sa-{idx}", "_summary": "{}"}

    def wait(self, handle, *, timeout):
        if handle.get("_timeout"):
            time.sleep(min(0.01, timeout))
            return {"completed": False, "timed_out": True, "state": "RUNNING"}
        state = handle.get("_state", "SUCCEEDED")
        return {"completed": True, "timed_out": False, "state": state}

    def result(self, handle):
        return {"terminal_state": handle.get("_state", "SUCCEEDED"),
                "summary": handle.get("_summary"),
                "error_message": handle.get("_error"),
                "error_classification": "FAILED" if handle.get("_state") == "FAILED" else None}

    def cancel(self, handle, *, reason):
        self.cancelled.append(reason)
        return True


def make_queue(tmp, files=2):
    store = BatchStore(os.path.join(tmp, "b.db"))
    q = BatchQueue(store)
    gid = q.create_group(
        plan=plan_batches([FileItem(path=f"src/C{i:03d}.vue", size=100) for i in range(files)],
                          BatchPolicy(max_files_per_batch=files)),
        run_id="r1", node_id="transform", expert_id="code-transformer",
        policy=BatchPolicy(max_files_per_batch=files, max_split_depth=2, max_attempts=2))
    return q, gid, store


class DriverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        self.work = Path(self.tmp) / "work"
        (self.work / "src").mkdir(parents=True)
        for i in range(8):
            (self.work / "src" / f"C{i:03d}.vue").write_text("<template>v2</template>", encoding="utf-8")

    def driver(self, q, launcher):
        return BatchAutoDriver(q, launcher, staging_base=Path(self.tmp) / "staging",
                               project_root=str(self.work),
                               lock_dir=Path(self.tmp) / "locks")

    def test_success_apply_and_done(self):
        q, gid, store = make_queue(self.tmp, 3)
        launcher = FakeLauncher(["success"], str(self.work))
        out = self.driver(q, launcher).drive(gid, max_batches=5, max_seconds=30)
        self.assertTrue(out.done, out.to_dict())
        self.assertEqual(out.batches_done, out.batches_total)
        self.assertEqual((self.work / "src" / "C000.vue").read_text(encoding="utf-8"),
                         "<template>v3</template>")
        self.assertEqual(store.get_batch(f"{gid}--b0001").status, "done")
        store.close()

    def test_truncated_splits_and_completes(self):
        q, gid, store = make_queue(self.tmp, 4)
        # 第一次截断 → split 成 2 批；之后各批成功
        launcher = FakeLauncher(["truncated", "success", "success"], str(self.work))
        out = self.driver(q, launcher).drive(gid, max_batches=10, max_seconds=30)
        self.assertTrue(out.done, out.to_dict())
        actions = [e.action for e in out.events]
        self.assertIn("split", actions)
        self.assertEqual(out.batches_total, 3)
        store.close()

    def test_invalid_json_gets_one_correction(self):
        q, gid, store = make_queue(self.tmp, 1)
        launcher = FakeLauncher(["invalid", "success"], str(self.work))
        out = self.driver(q, launcher).drive(gid, max_batches=2, max_seconds=30)
        self.assertTrue(out.done, out.to_dict())
        self.assertEqual(len(launcher.launched), 2)
        self.assertTrue(launcher.launched[1]["metadata"].get("correction") is True)
        store.close()

    def test_rate_limit_requeues_without_consuming_attempt(self):
        q, gid, store = make_queue(self.tmp, 1)
        launcher = FakeLauncher(["rate_limit"], str(self.work))
        out = self.driver(q, launcher).drive(gid, max_batches=2, max_seconds=10)
        self.assertTrue(out.rate_limited, out.to_dict())
        self.assertFalse(out.ok)
        batch = store.get_batch(f"{gid}--b0001")
        self.assertEqual(batch.status, "ready")
        self.assertEqual(batch.attempt, 0)
        store.close()

    def test_timeout_fails_batch(self):
        q, gid, store = make_queue(self.tmp, 1)
        launcher = FakeLauncher(["timeout"], str(self.work))
        out = self.driver(q, launcher).drive(gid, max_batches=1, max_seconds=2, poll_slice=0.2)
        self.assertEqual([e.action for e in out.events], ["failed"])
        batch = store.get_batch(f"{gid}--b0001")
        self.assertEqual(batch.status, "ready")  # attempt 1 < max_attempts 2，可重试
        store.close()

    def test_singleton_lock(self):
        q, gid, store = make_queue(self.tmp, 1)
        lock = FileLock(Path(self.tmp) / "locks", gid, ttl_seconds=60)
        self.assertTrue(lock.acquire())
        out = self.driver(q, FakeLauncher(["success"], str(self.work))).drive(gid)
        self.assertTrue(out.busy)
        lock.release()
        store.close()

    def test_out_of_scope_write_detected_and_rolled_back(self):
        q, gid, store = make_queue(self.tmp, 1)
        launcher = FakeLauncher(["drift"], str(self.work))
        out = self.driver(q, launcher).drive(gid, max_batches=1, max_seconds=10)
        self.assertTrue(out.write_scope_violation, out.to_dict())
        self.assertEqual(out.events[0].action, "drift")
        self.assertIn("FLOW_BATCH_WRITE_SCOPE", out.events[0].error)
        self.assertFalse((self.work / "outside.txt").exists())
        batch = store.get_batch(f"{gid}--b0001")
        self.assertTrue(batch.verdict.startswith("FLOW_BATCH_WRITE_SCOPE"), batch.verdict)
        store.close()

    def test_parse_summary_tolerates_fences_and_prose(self):
        text = '转换完成。\n```json\n{"files":[{"path":"a.vue","status":"done"}],"score":90}\n```\n'
        parsed = parse_child_summary(text)
        self.assertEqual(parsed["score"], 90)


if __name__ == "__main__":
    unittest.main()
