"""R3 浏览器探针的静态单测（不启动 Chrome，避免测试环境依赖）。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow_core.quality.browser import detect_routes, find_chrome


class BrowserUtilTest(unittest.TestCase):
    def test_detect_routes_from_router(self):
        sample = Path(r"E:\deepSeek\plugin\r2-work")
        if not (sample / "src" / "router" / "index.js").is_file():
            self.skipTest("r2-work fixture unavailable")
        routes = detect_routes(sample)
        self.assertIn("/", routes)
        self.assertIn("/home", routes)
        self.assertIn("/users", routes)
        self.assertIn("/about", routes)

    def test_find_chrome_or_skip(self):
        chrome = find_chrome()
        if chrome is None:
            self.skipTest("Chrome/Edge not installed on this host")
        self.assertTrue(Path(chrome).is_file())


if __name__ == "__main__":
    unittest.main()
