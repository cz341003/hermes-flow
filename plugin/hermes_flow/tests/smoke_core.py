import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flow_core.registry import Registry
from flow_core.batch import FileItem, BatchPolicy, plan_batches, BatchStore, BatchQueue
from flow_core.quality.batch_gate import evaluate_batch, aggregate_gate

ROOT = Path(__file__).resolve().parents[1]
root = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
reg = Registry(str(ROOT), root)
sk = reg.create_skill("Vue3 语法升级", "Vue3 syntax upgrade", "## Procedure\n1. transform")
a = reg.create_agent({
    "name": "代码转化专家",
    "role": "你是 Vue2 到 Vue3 迁移专家，负责逐文件转化并保持行为不变。",
    "skills": [sk.id],
})
print("agent", a.id, "skills", a.skills)

files = [FileItem(path=f"src/f{i}.vue", size=2000,
                  deps=([f"src/f{i-1}.vue"] if i % 5 else []),
                  risk="high" if i % 17 == 0 else "low") for i in range(287)]
plan = plan_batches(files, BatchPolicy())
print("batches", plan.total_batches, "waves", plan.waves, "files", plan.total_files)

store = BatchStore(os.path.join(root, "batch.db"))
q = BatchQueue(store)
gid = q.create_group(plan=plan, run_id="r1", node_id="transform", expert_id=a.id)
b = q.claim_next(gid, "driver")
print("claim", b.id if b else None, b.status if b else None)
res = q.ingest(b.id, [{"path": f["path"], "status": "done"} for f in b.files], attempt_id="1")
print("ingest", res)
q.complete(b.id, score=90, verdict="pass")
st = q.status(gid)
print("status", st["done_batches"], "/", st["total_batches"])
print(evaluate_batch(ast_ok=True, diff_ok=True, llm_score=90))
print(aggregate_gate(batch_scores=[88, 91], coverage=1.0, full_build_ok=True, browser_ok=True))
store.close()
print("OK")
