"""R4 工作区写入边界审计单测。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.batch.audit import WorkspaceAudit


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())
        self.root = Path(self.tmp) / "proj"
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "A.vue").write_text("a", encoding="utf-8")
        (self.root / "src" / "B.vue").write_text("b", encoding="utf-8")
        (self.root / "package.json").write_text("{}", encoding="utf-8")
        self.audit = WorkspaceAudit(self.root, Path(self.tmp) / "audit")

    def test_clean_changes_in_allowed_paths(self):
        self.audit.ensure_baseline()
        (self.root / "src" / "A.vue").write_text("a2", encoding="utf-8")
        out = self.audit.audit(["src/A.vue"])
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["violations"], [])

    def test_modified_outside_rolls_back(self):
        self.audit.ensure_baseline()
        (self.root / "src" / "B.vue").write_text("hacked", encoding="utf-8")
        out = self.audit.audit(["src/A.vue"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["violations"][0]["path"], "src/B.vue")
        self.assertEqual((self.root / "src" / "B.vue").read_text(encoding="utf-8"), "b")
        self.assertIn("src/B.vue", out["restored"])

    def test_created_outside_removed(self):
        self.audit.ensure_baseline()
        (self.root / "rogue.js").write_text("x", encoding="utf-8")
        out = self.audit.audit(["src/A.vue"])
        self.assertFalse(out["ok"])
        self.assertFalse((self.root / "rogue.js").exists())
        self.assertIn("rogue.js", out["removed"])

    def test_deleted_outside_restored(self):
        self.audit.ensure_baseline()
        (self.root / "package.json").unlink()
        out = self.audit.audit(["src/A.vue"])
        self.assertFalse(out["ok"])
        self.assertTrue((self.root / "package.json").exists())
        self.assertEqual((self.root / "package.json").read_text(encoding="utf-8"), "{}")


if __name__ == "__main__":
    unittest.main()
