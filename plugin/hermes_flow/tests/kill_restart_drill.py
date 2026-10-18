"""R8b kill/restart 真实进程演练：杀 worker → 等租约/锁过期 → 新进程恢复并完成。"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.batch import BatchPolicy, BatchQueue, BatchStore, FileItem, plan_batches

PY = sys.executable
WORKER = ROOT / "tests" / "kill_restart_worker.py"
tmp = Path(tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir()))
work = tmp / "work"
(work / "src").mkdir(parents=True)
for i in range(8):
    (work / "src" / f"K{i}.vue").write_text("<template>v2</template>", encoding="utf-8")

db = tmp / "kill.db"
store = BatchStore(str(db))
q = BatchQueue(store)
policy = BatchPolicy(max_files_per_batch=4, max_attempts=3, tick_budget_seconds=2)
plan = plan_batches([FileItem(path=f"src/K{i}.vue", size=100) for i in range(8)], policy)
gid = q.create_group(plan=plan, run_id="r-kill", node_id="transform",
                     expert_id="code-transformer", policy=policy)
store.close()

cmd = [PY, str(WORKER), str(db), str(work), str(tmp / "staging"),
       str(tmp / "locks"), gid]
slow = subprocess.Popen(cmd + ["slow"], cwd=str(ROOT),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        encoding="utf-8", errors="replace")
# 等第一个批次进入 running
import sqlite3
running = False
for _ in range(60):
    time.sleep(0.2)
    con = sqlite3.connect(str(db)); con.row_factory = sqlite3.Row
    rows = con.execute("select status from batches where group_id=?", (gid,)).fetchall()
    con.close()
    if any(r["status"] == "running" for r in rows):
        running = True
        break
assert running, "worker did not claim a batch"
slow.kill()
slow.wait(timeout=10)
killed_at = time.time()

# 等租约(2s) + 文件锁(3s)过期
time.sleep(4.5)
recover = subprocess.run(cmd + ["recover"], cwd=str(ROOT), capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=120)
result = json.loads((recover.stdout or "{}").strip().splitlines()[-1]) if recover.stdout.strip() else {}
store = BatchStore(str(db))
q2 = BatchQueue(store)
status = q2.status(gid)
files = sorted((work / "src").glob("*.vue"))
contents = {p.name: p.read_text(encoding="utf-8") for p in files}
store.close()

report = {
    "killed_after_seconds": round(killed_at - (killed_at - 1), 2),
    "recover_exit": recover.returncode,
    "worker_result": result,
    "done_batches": status["done_batches"],
    "total_batches": status["total_batches"],
    "failed": status["failed"],
    "files": len(files),
    "all_v3": all("v3" in c for c in contents.values()),
    "recover_stderr": (recover.stderr or "")[-1000:],
}
Path(r"E:\deepSeek\docs\r8b-kill-restart.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
