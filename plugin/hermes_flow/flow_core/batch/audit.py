"""工作区写入边界审计（FR-10 / B11）。

- 首次 driver 进入 group 时，对项目做一次基线快照（哈希 + 完整文件备份，排除依赖/构建产物）。
- 每批 apply 后对比当前工作区与基线；`post - pre - 组内文件集合` 非空即越界写。
- 越界文件从基线备份恢复；基线中不存在的新文件删除；返回证据并让批次以
  `FLOW_BATCH_WRITE_SCOPE` 失败，等待人工门/重试。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

DEFAULT_EXCLUDES = (
    "node_modules", ".git", "dist", "build", "coverage", ".next", ".nuxt",
    ".quality-tmp", ".quality-browser", ".vite", ".cache", ".tmp",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: Path, excludes: Iterable[str]) -> Iterable[Path]:
    excluded = set(excludes)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in excluded for part in rel_parts):
            continue
        yield path


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


class WorkspaceAudit:
    def __init__(self, project_root: str | Path, store_dir: str | Path,
                 excludes: Iterable[str] = DEFAULT_EXCLUDES):
        self.root = Path(project_root).resolve()
        self.store = Path(store_dir).resolve() / self.root.name
        self.excludes = tuple(excludes)

    def _manifest_path(self) -> Path:
        return self.store / "baseline.json"

    def _backup_root(self) -> Path:
        return self.store / "files"

    def ensure_baseline(self) -> Dict[str, Any]:
        """有则复用，无则复制项目源码 + 记录哈希。"""
        manifest = self._manifest_path()
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("root") == str(self.root):
                    return data
            except Exception:  # noqa: BLE001
                pass
        self.store.mkdir(parents=True, exist_ok=True)
        backup = self._backup_root()
        if backup.exists():
            shutil.rmtree(backup)
        entries: Dict[str, Dict[str, Any]] = {}
        for path in _iter_files(self.root, self.excludes):
            rel = _rel(self.root, path)
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            entries[rel] = {"sha256": _sha256(path), "size": path.stat().st_size}
        data = {"root": str(self.root), "at": time.time(), "files": entries}
        self._manifest_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for path in _iter_files(self.root, self.excludes):
            rel = _rel(self.root, path)
            out[rel] = {"sha256": _sha256(path), "size": path.stat().st_size}
        return out

    def audit(self, allowed_paths: Iterable[str]) -> Dict[str, Any]:
        """对比并回滚越界写；返回 {ok, violations, restored, removed}。"""
        manifest = self.ensure_baseline()
        before: Dict[str, Dict[str, Any]] = manifest.get("files") or {}
        now = self.snapshot()
        allowed: Set[str] = set()
        for p in allowed_paths:
            rel = str(p).replace("\\", "/")
            allowed.add(rel[2:] if rel.startswith("./") else rel)
        violations: List[Dict[str, str]] = []
        restored: List[str] = []
        removed: List[str] = []
        for rel, info in now.items():
            if rel in allowed:
                continue
            old = before.get(rel)
            if old is None:
                violations.append({"path": rel, "kind": "created"})
            elif old.get("sha256") != info.get("sha256"):
                violations.append({"path": rel, "kind": "modified"})
        for rel in before:
            if rel in allowed or rel in now:
                continue
            violations.append({"path": rel, "kind": "deleted"})
        for item in violations:
            rel = item["path"]
            backup = self._backup_root() / rel
            target = self.root / rel
            if item["kind"] == "created":
                try:
                    target.unlink()
                    removed.append(rel)
                except OSError:
                    pass
            else:
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
                    restored.append(rel)
                except OSError:
                    pass
        result = {
            "ok": not violations, "violations": violations,
            "restored": restored, "removed": removed,
            "allowed_count": len(allowed), "root": str(self.root),
            "at": time.time(),
        }
        if violations:
            evidence = self.store / f"violation-{int(result['at'])}.json"
            try:
                evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
                result["evidence_path"] = str(evidence)
            except OSError:
                pass
        return result
