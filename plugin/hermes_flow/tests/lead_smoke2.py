"""调度语义冒烟：组策略生效、租约过期抢占、截断 split 上限。"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

from hermes_flow.flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches
from hermes_flow.flow_core.engine.scheduler import ExecutionResult
from hermes_flow.flow_core.orchestrator import WorkflowOrchestrator

tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

# 1) 组策略：max_split_depth=1 必须生效（默认 2）
store = BatchStore(os.path.join(tmp, "p1.db"))
q = BatchQueue(store, BatchPolicy(max_split_depth=2))
gid = q.create_group(plan=plan_batches([FileItem(path=f"f{i}.vue", size=100) for i in range(4)],
                                       BatchPolicy(max_files_per_batch=4)),
                     run_id="r1", node_id="t", expert_id="e",
                     policy=BatchPolicy(max_files_per_batch=4, max_split_depth=1))
b = q.claim_next(gid, "t")
ids = q.split(b.id)
print("split first", b.id, "->", ids, "depth", store.get_batch(ids[0]).split_depth)
child = q.claim_next(gid, "t")
ids2 = q.split(child.id)
print("split child (depth1) ->", ids2, "expected []")
assert ids2 == []
store.close()

# 2) 租约过期可抢占
store = BatchStore(os.path.join(tmp, "p2.db"))
q = BatchQueue(store, BatchPolicy(tick_budget_seconds=1))
gid = q.create_group(plan=plan_batches([FileItem(path="a.vue", size=100)],
                                       BatchPolicy(max_files_per_batch=1)),
                     run_id="r2", node_id="t", expert_id="e",
                     policy=BatchPolicy(tick_budget_seconds=1))
b = q.claim_next(gid, "owner1")
print("claim1", b.id, b.attempt, "owner", b.lease_owner)
assert q.claim_next(gid, "owner2") is None
time.sleep(2.2)
b2 = q.claim_next(gid, "owner2")
print("claim2 after lease", b2.id if b2 else None, b2.attempt if b2 else None,
      b2.lease_owner if b2 else None)
assert b2 is not None and b2.attempt == 2 and b2.lease_owner == "owner2"
store.close()

# 3) orchestrator：恒截断 + max_split_depth=1 → 有界失败，不无限循环
def runner(node, ctx):
    return ExecutionResult(success=False, truncated=True, error="always truncated")

wf = {"id": "wf-split", "name": "split test", "nodes": [
    {"id": "transform", "type": "batch", "name": "t", "phase": "transform",
     "agent": "e", "batch": {"max_files_per_batch": 4, "max_split_depth": 1}},
], "edges": []}
store = BatchStore(os.path.join(tmp, "p3.db"))
q = BatchQueue(store)
orch = WorkflowOrchestrator(q)
res = orch.run(wf, runner, run_id="r3",
               files_by_node={"transform": [{"path": f"f{i}.vue", "size": 100} for i in range(4)]},
               expert_policies={"e": {"loop_policy": {"max_files_per_batch": 4, "max_split_depth": 1}}})
print("orchestrator truncated done", res.done, "failed", res.failed_nodes)
print("batches", res.batches["transform"]["done_batches"], "/", res.batches["transform"]["total_batches"])
assert res.done is False
store.close()
print("ALL OK")
