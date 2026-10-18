"""Lead 集成冒烟：workflow demo、批处理 apply/幂等、split/repair。"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

from hermes_flow.flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches
from hermes_flow.flow_core.engine.dag import Workflow, topological_sort
from hermes_flow.flow_core.orchestrator import WorkflowOrchestrator
from hermes_flow.flow_core.engine.scheduler import ExecutionResult
from hermes_flow.runtime import FlowRuntime

data_dir = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
rt = FlowRuntime(ROOT, data_dir)

WF = {
    "schema": "hermes-flow/workflow@1",
    "id": "vue3-migrate-6phase",
    "name": "Vue2→Vue3 六阶段",
    "version": "1.0.0",
    "nodes": [
        {"id": "analyze", "type": "agent_task", "name": "结构分析", "phase": "analyze",
         "agent": "structure-analyst"},
        {"id": "deps", "type": "agent_task", "name": "依赖分析", "phase": "deps",
         "agent": "dependency-analyst", "depends_on": ["analyze"]},
        {"id": "transform", "type": "batch", "name": "代码转化", "phase": "transform",
         "agent": "code-transformer", "depends_on": ["deps"],
         "batch": {"source": "inline", "order": "topo", "size": 7,
                   "context_budget_chars": 28000, "inner_loop": "serial",
                   "concurrency": 1, "max_split_depth": 2, "split_on_failure": True,
                   "quality_gate_per_batch": True, "write_mode": "staging_apply"}},
        {"id": "quality", "type": "quality_gate", "name": "质量评分", "phase": "quality",
         "depends_on": ["transform"]},
        {"id": "verify", "type": "agent_task", "name": "浏览器验证", "phase": "verify",
         "agent": "browser-verifier", "depends_on": ["quality"]},
        {"id": "review", "type": "human_gate", "name": "人工验收", "phase": "fix",
         "depends_on": ["verify"]},
    ],
    "edges": [
        {"source": "analyze", "target": "deps"},
        {"source": "deps", "target": "transform"},
        {"source": "transform", "target": "quality"},
        {"source": "quality", "target": "verify"},
        {"source": "verify", "target": "review"},
    ],
}
rt.registry.save_workflow(WF)
print("workflow saved", bool(rt.registry.get_workflow("vue3-migrate-6phase")))

files = [{"path": f"src/C{i:03d}.vue", "size": 1800,
          "deps": ([f"src/C{i-1:03d}.vue"] if i % 7 else []), "risk": "low"}
         for i in range(30)]
run = rt.start_run(workflow_id="vue3-migrate-6phase", project_root="", files=files)
print("run", run["id"])

plan = rt.batch_plan(run_id=run["id"], node_id="transform")
print("plan", plan["plan"]["total_batches"], "batches,", plan["group_id"])
packet = rt.batch_next(group_id=plan["group_id"])
print("packet files", len(packet["files"]), "staging", bool(packet["staging_root"]))

# ingest + complete 所有批次（模拟子代理 done）
first_packet = packet
packet = first_packet
while packet.get("batch_id"):
    rt.batch_ingest(group_id=plan["group_id"], batch_id=packet["batch_id"],
                    results=[{"path": f["path"], "status": "done"} for f in packet["files"]])
    rt.batch_complete(packet["batch_id"], score=90, verdict="pass")
    packet = rt.batch_next(group_id=plan["group_id"])
st = rt.batch_status(plan["group_id"])
print("batch status", st["done_batches"], "/", st["total_batches"])

# apply 到真实工作区
work = Path(tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir()))
(work / "src").mkdir(parents=True, exist_ok=True)
(work / "src" / "C000.vue").write_text("<template>v2</template>", encoding="utf-8")
staging = Path(first_packet["staging_root"])
(staging / "src").mkdir(parents=True, exist_ok=True)
(staging / "src" / "C000.vue").write_text("<template>v3</template>", encoding="utf-8")

# 单独建一个单批 group 验证 apply
items = [FileItem(path="src/C000.vue", size=100)]
st2 = BatchStore(str(Path(data_dir) / "apply.db"))
q2 = BatchQueue(st2)
gid = q2.create_group(plan=plan_batches(items, BatchPolicy()), run_id="r-apply",
                      node_id="transform", expert_id="code-transformer")
b = q2.claim_next(gid, "t")
q2.ingest(b.id, [{"path": "src/C000.vue", "status": "done",
                  "staged_path": str(staging / "src" / "C000.vue")}])
out = q2.apply(b.id, project_root=str(work), staging_root=str(staging),
               backup_root=str(Path(data_dir) / "backup"))
print("apply", out)
print("workspace content", (work / "src" / "C000.vue").read_text(encoding="utf-8"))
print("backup exists", (Path(data_dir) / "backup" / "src" / "C000.vue").exists())
st2.close()

# split / repair
store = BatchStore(str(Path(data_dir) / "sr.db"))
q = BatchQueue(store)
gid2 = q.create_group(plan=plan_batches([FileItem(path=f"f{i}.vue", size=100) for i in range(8)],
                                        BatchPolicy(max_files_per_batch=8)),
                      run_id="r2", node_id="t", expert_id="e")
b = q.claim_next(gid2, "t")
q.ingest(b.id, [{"path": "f0.vue", "status": "failed"}, {"path": "f1.vue", "status": "done"}])
rid = q.repair(b.id, ["f0.vue"])
print("repair", rid)
q.complete(b.id, score=60, verdict="rework")
q.complete(rid, score=90, verdict="pass")
print("repair status", q.status(gid2)["done_batches"], "/", q.status(gid2)["total_batches"])
store.close()

# orchestrator 全流程（mock runner）
queue = BatchQueue(BatchStore(str(Path(data_dir) / "orch.db")))
orch = WorkflowOrchestrator(queue)
result = orch.run(WF, lambda node, ctx: ExecutionResult(success=True, score=90),
                  run_id="r-orch", files_by_node={"transform": files})
print("orchestrator done", result.done, "trace", result.trace,
      "batches", result.batches.get("transform", {}).get("done_batches"))
assert result.done
print("ALL OK")
