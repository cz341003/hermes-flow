"""R8 指标采集：生成报告用的确定性数字。"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches
from flow_core.batch.driver import BatchAutoDriver
from tests.test_stress import StressLauncher

# 1000 文件规划
items = [FileItem(path=f"src/C{i:04d}.vue", size=1200,
                  deps=([f"src/C{i - 1:04d}.vue"] if i % 50 else []))
         for i in range(1000)]
plan = plan_batches(items, BatchPolicy(max_files_per_batch=7))
plan_metrics = {"files": 1000, "batches": len(plan.batches),
                "waves": len({b.wave for b in plan.batches}),
                "covered": sum(len(b.files) for b in plan.batches)}

# 100 批 + 10 次故障
tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
work = Path(tmp) / "work"
(work / "src").mkdir(parents=True)
store = BatchStore(os.path.join(tmp, "stress.db"))
q = BatchQueue(store)
files = [FileItem(path=f"src/S{i:04d}.vue", size=100) for i in range(700)]
policy = BatchPolicy(max_files_per_batch=7, max_attempts=3, max_split_depth=0)
p2 = plan_batches(files, policy)
gid = q.create_group(plan=p2, run_id="r-stress", node_id="transform",
                     expert_id="code-transformer", policy=policy)
launcher = StressLauncher(fail_first=10)
driver = BatchAutoDriver(q, launcher, staging_base=Path(tmp) / "staging",
                         project_root=str(work), lock_dir=Path(tmp) / "locks",
                         audit=False)
started = time.time()
out = driver.drive(gid, max_batches=200, max_seconds=300)
elapsed = time.time() - started
status = q.status(gid)
metrics = {
    "plan_1000": plan_metrics,
    "stress": {"batches": status["total_batches"], "done": status["done_batches"],
               "failed": len(status["failed"]), "launches": launcher.launched,
               "injected": len(launcher.failed), "elapsed_seconds": round(elapsed, 3),
               "done_flag": out.done},
    "timestamp": time.time(),
}
Path(r"E:\deepSeek\docs\r8-metrics.json").write_text(
    json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
store.close()
print(json.dumps(metrics, ensure_ascii=False, indent=2))
