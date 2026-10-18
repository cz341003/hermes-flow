"""kill/restart 演练 worker：slow 模式阻塞（用于被杀），recover 模式完成批次。"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.batch import BatchQueue, BatchStore
from flow_core.batch.driver import BatchAutoDriver

db, work, staging, locks, group, mode = sys.argv[1:7]


class Launcher:
    def __init__(self, mode):
        self.mode = mode
        self.n = 0

    def launch(self, *, goal, context, metadata, correlation_id):
        self.n += 1
        if self.mode == "slow":
            time.sleep(60)  # 等父进程 kill
        payload = json.loads(context)
        for f in payload.get("files", []):
            p = Path(f["staging_path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("<template>v3</template>", encoding="utf-8")
        summary = json.dumps({"files": [{"path": f["path"], "status": "done"}
                                        for f in payload.get("files", [])], "score": 92})
        return {"subagent_id": f"sa-{self.n}", "_summary": summary}

    def wait(self, handle, *, timeout):
        return {"completed": True, "timed_out": False, "state": "SUCCEEDED"}

    def result(self, handle):
        return {"terminal_state": "SUCCEEDED", "summary": handle.get("_summary"),
                "error_message": None, "error_classification": None}

    def cancel(self, handle, *, reason):
        return True


store = BatchStore(db)
queue = BatchQueue(store)
driver = BatchAutoDriver(queue, Launcher(mode), staging_base=staging,
                         project_root=work, lock_dir=locks, audit=False,
                         lock_ttl_seconds=3)
out = driver.drive(group, max_batches=10, max_seconds=60)
print(json.dumps(out.to_dict(), ensure_ascii=False))
store.close()
