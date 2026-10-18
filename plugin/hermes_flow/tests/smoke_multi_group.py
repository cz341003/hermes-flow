import os
import sys
import tempfile

sys.path.insert(0, r"E:\deepSeek\plugin")
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
from hermes_flow.flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches

d = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
s = BatchStore(os.path.join(d, "multi.db"))
q = BatchQueue(s)
g1 = q.create_group(plan=plan_batches([FileItem(path="a.vue")], BatchPolicy()), run_id="r1", node_id="t", expert_id="e")
g2 = q.create_group(plan=plan_batches([FileItem(path="b.vue")], BatchPolicy()), run_id="r2", node_id="t", expert_id="e")
b1 = q.claim_next(g1, "o")
b2 = q.claim_next(g2, "o")
print("groups", g1, g2, "batch ids", b1.id, b2.id)
assert b1.id != b2.id
q.ingest(b1.id, [{"path": "a.vue", "status": "done"}])
q.complete(b1.id, score=90)
q.ingest(b2.id, [{"path": "b.vue", "status": "done"}])
q.complete(b2.id, score=90)
print("status", q.status(g1)["done_batches"], q.status(g2)["done_batches"])
print("OK")
