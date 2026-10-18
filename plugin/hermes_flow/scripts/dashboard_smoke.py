#!/usr/bin/env python3
"""Dashboard 静态冒烟：manifest 完整、bundle/CSS 存在且版本一致。"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"


def main() -> int:
    version = re.search(r"^version:\s*(\S+)", (ROOT / "plugin.yaml").read_text(encoding="utf-8"),
                        re.M).group(1)
    manifest = json.loads((DASH / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version, (manifest["version"], version)
    assert manifest["name"] == "hermes_flow"
    assert manifest["tab"]["path"] == "/flow"
    for key in ("entry", "css"):
        p = DASH / manifest[key]
        assert p.is_file(), f"missing {key}: {p}"
        assert p.stat().st_size > 1000, f"{key} too small"
    bundle = (DASH / manifest["entry"]).read_text(encoding="utf-8", errors="replace")
    assert "hermes_flow" in bundle, "bundle missing plugin name"
    print(f"dashboard smoke OK: v{version}, {len(bundle)} bytes bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
