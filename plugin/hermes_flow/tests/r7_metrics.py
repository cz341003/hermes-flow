"""R7 指标：并行/串行对比、worktree 数量、提交顺序。"""
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
from tests.test_parallel import ParallelLauncher


def run(concurrency):
    tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
    work = Path(tmp) / "work"
    (work / "src").mkdir(parents=True)
    for i in range(9):
        (work / "src" / f"P{i}.vue").write_text("<template>v2</template>", encoding="utf-8")
    store = BatchStore(os.path.join(tmp, "p.db"))
    q = BatchQueue(store)
    policy = BatchPolicy(max_files_per_batch=3, max_concurrent_batches=concurrency,
                         max_attempts=2)
    plan = plan_batches([FileItem(path=f"src/P{i}.vue", size=100) for i in range(9)], policy)
    gid = q.create_group(plan=plan, run_id="r7", node_id="transform",
                         expert_id="code-transformer", policy=policy)
    launcher = ParallelLauncher(work)
    driver = BatchAutoDriver(q, launcher, staging_base=Path(tmp) / "staging",
                             project_root=str(work), lock_dir=Path(tmp) / "locks",
                             worktree_base=Path(tmp) / "worktrees", audit=False,
                             concurrency=concurrency)
    started = time.time()
    out = driver.drive(gid, max_batches=3, max_seconds=30)
    elapsed = time.time() - started
    order = [e.batch_id for e in out.events if e.action == "done"]
    worktrees = list((Path(tmp) / "worktrees").rglob("*.vue"))
    store.close()
    return {"concurrency": concurrency, "done": out.done, "batches": out.batches_done,
            "max_active": launcher.max_active, "elapsed_seconds": round(elapsed, 3),
            "stable_order": order == sorted(order), "worktree_files": len(worktrees)}


metrics = {"serial": run(1), "parallel": run(3)}
Path(r"E:\DeepSeek\docs\r7-metrics.json").write_text(
    json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(metrics, ensure_ascii=False, indent=2))
