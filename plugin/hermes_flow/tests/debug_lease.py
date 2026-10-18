import os
import sys
import tempfile
import time

sys.path.insert(0, r"E:\deepSeek\plugin")
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
d = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
from hermes_flow.flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches

s = BatchStore(os.path.join(d, "x.db"))
q = BatchQueue(s, BatchPolicy(tick_budget_seconds=1))
g = q.create_group(plan=plan_batches([FileItem(path="a.vue", size=100)], BatchPolicy()),
                   run_id="r", node_id="t", expert_id="e",
                   policy=BatchPolicy(tick_budget_seconds=1))
b = q.claim_next(g, "o1")
print("policy", s.get_group_policy(g))
print("batch", b.id, b.lease_expires_at, int(time.time()))
time.sleep(2.2)
print("now", int(time.time()))
rows = s._execute("select id,status,attempt,lease_owner,lease_expires_at,version from batches").fetchall()
print("rows", [dict(r) for r in rows])
print("claim2", q.claim_next(g, "o2"))
s.close()
