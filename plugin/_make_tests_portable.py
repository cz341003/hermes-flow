from pathlib import Path

ROOT = Path(r"E:\deepSeek\plugin\hermes_flow\tests")
OLD_MK = 'tempfile.mkdtemp(dir=r"E:\\deepSeek\\plugin\\.tmp")'
NEW_MK = 'tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())'
OLD_PATH = 'Path(r"E:\\deepSeek\\plugin\\.tmp")'
NEW_PATH = 'Path(os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())'

changed = []
for path in sorted(ROOT.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace(OLD_MK, NEW_MK).replace(OLD_PATH, NEW_PATH)
    if "import os" not in text and "os." in text and "import tempfile" in text:
        text = text.replace("import tempfile", "import os\nimport tempfile", 1)
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed.append(path.name)
print("changed", changed)
