import json
import os
import sys
from pathlib import Path

ROOT = Path(r"E:\deepSeek\plugin\hermes_flow")
sys.path.insert(0, str(ROOT.parent))
os.environ["HERMES_HOME"] = r"E:\hermes"

from hermes_flow.runtime import FlowRuntime  # noqa: E402

rt = FlowRuntime(ROOT, Path(r"E:\hermes\plugin-data\hermes_flow"))
run = rt.start_run(workflow_id="vue3-migrate-6phase",
                   project_root=r"E:\deepSeek\plugin\auto-e2e",
                   files=[{"path": "src/A.vue", "size": 131},
                          {"path": "src/B.vue", "size": 131}],
                   title="R5b 事件流演示")
plan = rt.batch_plan(run_id=run["id"], node_id="transform")
print(json.dumps({"run_id": run["id"], "group_id": plan["group_id"],
                  "events": rt.run_events(run["id"])["events"]}, ensure_ascii=False, indent=2))
