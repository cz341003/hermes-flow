"""R3 真实质量采集器单测。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.quality.collectors import collect, collect_for_gate, detect_commands


def make_project(tmp, build_ok=True):
    root = Path(tmp) / "proj"
    root.mkdir()
    script = "node -e \"process.exit(0)\"" if build_ok else "node -e \"process.exit(1)\""
    (root / "package.json").write_text(json.dumps({
        "name": "sample", "scripts": {"build": script, "type-check": "node -e \"process.exit(0)\""},
        "devDependencies": {"vite": "^5.0.0"},
    }), encoding="utf-8")
    return root


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

    def test_detect_commands(self):
        root = make_project(self.tmp)
        cmds = detect_commands(root)
        self.assertEqual(cmds["build"], ["npm", "run", "build"])
        self.assertEqual(cmds["typecheck"], ["npm", "run", "type-check"])

    def test_collect_success(self):
        root = make_project(self.tmp, build_ok=True)
        out = collect(root, build=True, typecheck=True, timeout=120)
        self.assertTrue(out["build"]["ran"])
        self.assertTrue(out["build"]["ok"], out["build"])
        self.assertTrue(out["ok"], out)
        self.assertIn("build", out["commands"])

    def test_collect_failure(self):
        root = make_project(self.tmp, build_ok=False)
        out = collect(root, build=True, typecheck=False, timeout=120)
        self.assertTrue(out["build"]["ran"])
        self.assertFalse(out["build"]["ok"])
        self.assertFalse(out["ok"])

    def test_typecheck_skipped_without_config(self):
        root = make_project(self.tmp)
        (root / "package.json").write_text(json.dumps({"name": "x", "scripts": {"build": "node -e \"process.exit(0)\""}}),
                                           encoding="utf-8")
        out = collect(root, build=False, typecheck=True, timeout=60)
        self.assertTrue(out["typecheck"]["skipped"])

    def test_collect_for_gate_signals(self):
        root = make_project(self.tmp)
        out = collect_for_gate(root, timeout=120)
        self.assertIn("full_build_ok", out)
        self.assertIn("signals", out)
        self.assertTrue(out["full_build_ok"])


if __name__ == "__main__":
    unittest.main()
