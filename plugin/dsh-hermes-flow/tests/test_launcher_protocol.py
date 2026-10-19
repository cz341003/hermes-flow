"""协议级测试：Python sidecar 的 batch_auto ↔ 假 DSH launch 回调。"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIDECAR = HERE.parent / "sidecar" / "rpc.py"
PY = os.environ.get("HERMES_FLOW_PYTHON") or sys.executable
ROOT = Path(os.environ.get("HERMES_FLOW_PLUGIN_ROOT", r"E:\deepSeek\plugin\hermes_flow"))

tmp = Path(tempfile.mkdtemp(prefix="dsh-flow-test-"))
project = tmp / "project"
(project / "src").mkdir(parents=True)
(project / "src" / "A.vue").write_text("<template>v2</template>", encoding="utf-8")

env = dict(os.environ)
env.update({
    "HERMES_FLOW_PLUGIN_ROOT": str(ROOT),
    "HERMES_FLOW_DATA_DIR": str(tmp / "data"),
    "PYTHONIOENCODING": "utf-8",
})
proc = subprocess.Popen([PY, str(SIDECAR)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)


def send(obj):
    proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def wait_for(req_id, on_launch=None):
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("sidecar exited: " + proc.stderr.read())
        msg = json.loads(line)
        if msg.get("method") == "__launch__":
            params = msg.get("params") or {}
            files = (json.loads(params.get("context") or "{}") or {}).get("files", [])
            for f in files:
                p = Path(f["staging_path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("<template>v3</template>", encoding="utf-8")
            summary = json.dumps({"files": [{"path": f["path"], "status": "done"} for f in files],
                                  "score": 95, "truncated": False})
            if on_launch:
                on_launch(params)
            send({"id": msg["id"], "ok": True, "result": {
                "terminal_state": "SUCCEEDED", "summary": summary, "child_id": "fake-dsh-child"}})
            continue
        if str(msg.get("id")) == str(req_id):
            if not msg.get("ok"):
                raise RuntimeError(msg.get("error"))
            return msg.get("result")


send({"id": 1, "method": "run_start", "params": {
    "workflow_id": "vue3-migrate-6phase", "project_root": str(project),
    "files": [{"path": "src/A.vue", "size": 20}]}})
run = wait_for(1)
send({"id": 2, "method": "batch_plan", "params": {
    "run_id": run["id"], "node_id": "transform",
    "policy": {"max_files_per_batch": 1, "max_attempts": 1, "max_split_depth": 0}}})
plan = wait_for(2)
send({"id": 3, "method": "batch_auto", "params": {
    "group_id": plan["group_id"], "max_batches": 2, "max_seconds": 30,
    "apply": True, "audit": False, "concurrency": 1}})
out = wait_for(3)
send({"id": 4, "method": "shutdown"})
proc.wait(timeout=10)
assert out.get("done") is True, out
assert out.get("batches_done") == 1, out
assert "v3" in (project / "src" / "A.vue").read_text(encoding="utf-8")
print(json.dumps({"ok": True, "run": run["id"], "group": plan["group_id"],
                  "batches_done": out["batches_done"], "child": "fake-dsh-child"}, ensure_ascii=False))
