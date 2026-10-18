"""工具层端到端冒烟：通过 fake ctx 注册后，用 handler 走完 Run→批次→门控→经验。"""
import json
import os
import sys
import tempfile
from pathlib import Path

PARENT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PARENT))
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

import hermes_flow  # noqa: E402
from hermes_flow import tools  # noqa: E402


class FakeCtx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, **kw):
        self.tools[name] = kw

    def register_hook(self, name, cb):
        pass

    def register_cli_command(self, name, **kw):
        pass


ctx = FakeCtx()
hermes_flow.register(ctx)


def call(name, args):
    return json.loads(ctx.tools[name]["handler"](args))


wf = call("flow_workflow_list", {})
wid = wf["data"]["workflows"][0]["id"]
print("workflow", wid)
files = [{"path": f"src/C{i:03d}.vue", "size": 1800,
          "deps": ([f"src/C{i-1:03d}.vue"] if i % 5 else []), "risk": "low"}
         for i in range(12)]
run = call("flow_run_start", {"workflow_id": wid, "project_root": "",
                             "files": files})["data"]
print("run", run["id"])
node = next(n["id"] for n in
            call("flow_workflow_get", {"workflow_id": wid})["data"]["definition"]["nodes"]
            if n.get("type") == "batch")
plan = call("flow_batch_plan", {"run_id": run["id"], "node_id": node})["data"]
print("plan", plan["plan"]["total_batches"], "batches")
gid = plan["group_id"]

done = 0
packet = call("flow_batch_next", {"group_id": gid})["data"]
while packet.get("batch_id"):
    res = call("flow_batch_ingest", {
        "group_id": gid, "batch_id": packet["batch_id"],
        "results": [{"path": f["path"], "status": "done"} for f in packet["files"]],
    })
    assert res["ok"], res
    call("flow_batch_complete", {"batch_id": packet["batch_id"], "score": 90, "verdict": "pass"})
    done += 1
    packet = call("flow_batch_next", {"group_id": gid})["data"]
status = call("flow_batch_status", {"group_id": gid})["data"]
print("batches done", status["done_batches"], "/", status["total_batches"])
assert done == status["total_batches"] == status["done_batches"]

gate = call("flow_gate_score", {"ast_ok": True, "diff_ok": True, "llm_score": 90})["data"]
print("gate", gate)
assert gate["verdict"] == "pass"

exp = call("flow_experience_add", {"category": "antdv", "trigger": "scopedSlots",
                                   "solution": "use #default"})
print("experience add", exp["ok"])
found = call("flow_experience_search", {"query": "scopedSlots"})["data"]["experiences"]
print("experience search", len(found))
assert found

out = os.path.join(tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir()), "board.html")
board = call("flow_board_render", {"out": out})["data"]
print("board", board["size"], Path(out).exists())
assert Path(out).exists()
print("TOOLS E2E OK")
