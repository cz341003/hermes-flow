"""R2 准备：复制 sample-app 到 r2-work，建 Run + 批次组。"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "hermes_flow"
sys.path.insert(0, str(ROOT.parent))
os.environ["HERMES_HOME"] = r"E:\hermes"

from hermes_flow.runtime import FlowRuntime  # noqa: E402

DATA_DIR = Path(r"E:\hermes\plugin-data\hermes_flow")
SRC = Path(r"E:\deepSeek\plugin\sample-app")
WORK = Path(r"E:\deepSeek\plugin\r2-work")

if WORK.exists():
    shutil.rmtree(WORK)
shutil.copytree(SRC, WORK)

DEPS = {
    "src/utils/format.js": [],
    "src/utils/request.js": [],
    "src/mixins/loadingMixin.js": [],
    "src/styles/variables.less": [],
    "src/styles/global.less": ["src/styles/variables.less"],
    "src/store/modules/user.js": ["src/utils/request.js"],
    "src/store/index.js": ["src/store/modules/user.js"],
    "src/components/HelloWorld.vue": ["src/mixins/loadingMixin.js", "src/utils/format.js"],
    "src/components/UserCard.vue": ["src/mixins/loadingMixin.js", "src/utils/format.js"],
    "src/components/TreeMenu.vue": ["src/utils/format.js"],
    "src/views/Home.vue": ["src/components/HelloWorld.vue", "src/utils/request.js"],
    "src/views/About.vue": ["src/components/UserCard.vue"],
    "src/views/UserList.vue": ["src/components/UserCard.vue", "src/store/modules/user.js"],
    "src/router/index.js": ["src/views/Home.vue", "src/views/About.vue", "src/views/UserList.vue"],
    "src/App.vue": ["src/components/TreeMenu.vue"],
    "src/main.js": ["src/App.vue", "src/router/index.js", "src/store/index.js"],
}
HIGH = {"src/main.js", "src/router/index.js", "src/store/index.js"}

files = []
for p in sorted(WORK.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(WORK).as_posix()
    if rel.startswith(("node_modules/", "dist/", ".git/")):
        continue
    files.append({"path": rel, "size": p.stat().st_size,
                  "deps": DEPS.get(rel, []),
                  "risk": "high" if rel in HIGH else "low"})

rt = FlowRuntime(ROOT, DATA_DIR)
run = rt.start_run(workflow_id="vue3-migrate-6phase", project_root=str(WORK),
                   files=files, title="R2 sample-app 20 files")
plan = rt.batch_plan(run_id=run["id"], node_id="transform")
out = {"run_id": run["id"], "group_id": plan["group_id"],
       "work": str(WORK), "files": len(files),
       "batches": plan["plan"]["total_batches"],
       "waves": plan["plan"].get("total_waves") or plan["plan"].get("waves"),
       "file_list": files}
Path(r"E:\deepSeek\plugin\r2-run.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: out[k] for k in ("run_id", "group_id", "files", "batches", "waves")},
                 ensure_ascii=False))
