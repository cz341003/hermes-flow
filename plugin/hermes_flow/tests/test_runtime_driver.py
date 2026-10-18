"""R1 运行时集成：FlowRuntime.auto_drive 用 fake lifecycle 跑完整批次组。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
os.environ.setdefault("HERMES_HOME", tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir()))

from hermes_flow.runtime import FlowRuntime  # noqa: E402

PLUGIN_ROOT = ROOT


class FakeHandle:
    def __init__(self, ident):
        self.subagent_id = ident

    def to_dict(self):
        return {"subagent_id": self.subagent_id}


class FakeLifecycle:
    def __init__(self, work):
        self.work = Path(work)
        self.launches = 0

    def launch(self, request):
        self.launches += 1
        ctx = request.get("context") or ""
        raw = ctx[ctx.find("{"):ctx.rfind("}") + 1]
        payload = json.loads(raw)
        for f in payload["files"]:
            sp = Path(f["staging_path"])
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text("<template>v3</template>", encoding="utf-8")
        self._summary = json.dumps({
            "files": [{"path": f["path"], "status": "done"} for f in payload["files"]],
            "score": 92, "truncated": False,
        })
        return FakeHandle(f"sa-{self.launches}")

    def wait(self, handle, timeout_seconds=None):
        return SimpleNamespace(completed=True, timed_out=False, state=SimpleNamespace(value="SUCCEEDED"))

    def result(self, handle):
        return SimpleNamespace(terminal_state=SimpleNamespace(value="SUCCEEDED"),
                               summary=self._summary, error_message=None,
                               error_classification=None)

    def cancel(self, handle, reason=""):
        return True


class RuntimeDriverTest(unittest.TestCase):
    def test_auto_drive_end_to_end(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        work = Path(tmp) / "work"
        (work / "src").mkdir(parents=True)
        for i in range(3):
            (work / "src" / f"C{i:03d}.vue").write_text("<template>v2</template>", encoding="utf-8")
        rt = FlowRuntime(PLUGIN_ROOT, Path(tmp) / "data")
        files = [{"path": f"src/C{i:03d}.vue", "size": 100} for i in range(3)]
        run = rt.start_run(workflow_id="vue3-migrate-6phase", project_root=str(work), files=files)
        plan = rt.batch_plan(run_id=run["id"], node_id="transform")
        lifecycle = FakeLifecycle(work)
        rt.set_lifecycle(lifecycle)
        out = rt.auto_drive(group_id=plan["group_id"], max_batches=10, max_seconds=60)
        self.assertTrue(out["done"], out)
        self.assertEqual(out["batches_done"], out["batches_total"])
        self.assertEqual((work / "src" / "C000.vue").read_text(encoding="utf-8"),
                         "<template>v3</template>")
        self.assertGreaterEqual(lifecycle.launches, 1)

    def test_no_lifecycle_returns_unavailable(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        rt = FlowRuntime(PLUGIN_ROOT, Path(tmp) / "data")
        out = rt.auto_drive(group_id="g-none")
        self.assertFalse(out["ok"])
        self.assertTrue(out["driver_unavailable"])


if __name__ == "__main__":
    unittest.main()
