import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(r"E:\deepSeek\plugin\hermes_flow")
sys.path.insert(0, str(ROOT.parent))
os.environ["HERMES_HOME"] = r"E:\hermes"

from hermes_flow.runtime import FlowRuntime  # noqa: E402

work = Path(r"E:\deepSeek\plugin\r8b-real")
if work.exists():
    shutil.rmtree(work)
(work / "src").mkdir(parents=True)
for name in "ABCDEF":
    (work / "src" / f"{name}.vue").write_text(
        '<template><div class="%s">{{ msg }}</div></template>\n'
        '<script>export default { data() { return { msg: "v2" } } }</script>\n' % name.lower(),
        encoding="utf-8")

rt = FlowRuntime(ROOT, Path(r"E:\hermes\plugin-data\hermes_flow"))
files = [{"path": f"src/{name}.vue", "size": 120} for name in "ABCDEF"]
run = rt.start_run(workflow_id="vue3-migrate-6phase", project_root=str(work),
                   files=files, title="R8b 6 文件真实并行采样")
plan = rt.batch_plan(run_id=run["id"], node_id="transform", policy={
    "max_files_per_batch": 2, "max_concurrent_batches": 3,
    "max_split_depth": 0, "context_budget_chars": 28000,
})
prompt = f"""你正在做 R8b 真实并行采样。Run 与批次组已创建：

flow_batch_auto(group_id="{plan['group_id']}", max_batches=5, max_seconds=300, apply=true, concurrency=3)

请调用一次，然后把完整 JSON 结果报告出来；如果 done=false 且无 failed/rate_limited，再调用一次同样的命令（最多 2 次）。最后调用 flow_batch_status(group_id="{plan['group_id']}") 报告 done/total。
不要安装依赖，不要修改 E:\\deepSeek\\plugin\\r8b-real 之外的文件。
"""
Path(r"E:\deepSeek\plugin\r8b_prompt.txt").write_text(prompt, encoding="utf-8")
print(json.dumps({"run_id": run["id"], "group_id": plan["group_id"],
                  "batches": plan["plan"]["total_batches"],
                  "files": 6}, ensure_ascii=False))
