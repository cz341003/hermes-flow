"""Checkpoint 持久化：把调度器状态跨会话存到磁盘，支持断点续跑。

默认用 JSON 文件（原子写：临时文件 + os.replace）。Scheduler 的 snapshot/from_snapshot
已在 engine 层提供；本模块负责落盘/读回。
"""
from __future__ import annotations

import json
import os
from typing import Optional

from ..engine import Scheduler


def snapshot_scheduler(sched: Scheduler) -> dict:
    return sched.snapshot()


def restore_scheduler(data: dict) -> Scheduler:
    return Scheduler.from_snapshot(data)


class JsonCheckpointStore:
    """按 workflow_id 保存/加载调度器快照的 JSON 文件存储。"""

    def __init__(self, path: str):
        self.path = path

    def save(self, workflow_id: str, sched: Scheduler) -> None:
        data = self._read_all()
        data[workflow_id] = sched.snapshot()
        self._write_all(data)

    def load(self, workflow_id: str) -> Optional[Scheduler]:
        data = self._read_all()
        snap = data.get(workflow_id)
        return restore_scheduler(snap) if snap else None

    def drop(self, workflow_id: str) -> None:
        data = self._read_all()
        if workflow_id in data:
            del data[workflow_id]
            self._write_all(data)

    def ids(self) -> list:
        return list(self._read_all().keys())

    # ------------------------------------------------------------------
    def _read_all(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_all(self, data: dict) -> None:
        directory = os.path.dirname(self.path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
