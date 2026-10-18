#!/usr/bin/env python3
"""打包 hermes_flow 插件为可发布的 zip，并生成 sha256。"""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r"^version:\s*(\S+)", (ROOT / "plugin.yaml").read_text(encoding="utf-8"),
                    re.M).group(1)
OUT = ROOT / "dist" / f"hermes_flow-{VERSION}.zip"
INCLUDE = ["plugin.yaml", "__init__.py", "cli.py", "tools.py", "runtime.py", "README.md",
           "CHANGELOG.md", "install.ps1", "install.sh", "flow_core", "agents", "skills",
           "workflows", "dashboard", "tests", "scripts"]
IGNORE = ("__pycache__", ".pyc", ".tmp", ".pytest_cache", "node_modules")


def iter_files():
    top_dist = (ROOT / "dist").resolve()
    for name in INCLUDE:
        p = ROOT / name
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file():
                    continue
                s = str(f)
                if any(x in s for x in IGNORE):
                    continue
                if f.suffix in (".zip", ".sha256"):
                    continue
                try:
                    f.resolve().relative_to(top_dist)
                    continue
                except ValueError:
                    pass
                yield f


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in iter_files():
            z.write(f, f.relative_to(ROOT).as_posix())
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    (OUT.with_suffix(".zip.sha256")).write_text(f"{digest}  {OUT.name}\n", encoding="utf-8")
    print(f"packed {OUT} ({OUT.stat().st_size} bytes)")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
