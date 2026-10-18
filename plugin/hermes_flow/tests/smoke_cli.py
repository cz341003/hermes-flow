"""CLI 冒烟：用 argparse 模拟 hermes flow 子命令。"""
import argparse
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

from hermes_flow import cli

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="root")
flow = sub.add_parser("flow")
cli.setup(flow)

for argv in (["flow", "status"], ["flow", "agents"], ["flow", "workflows"]):
    ns = parser.parse_args(argv)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.run(ns)
    out = buf.getvalue()
    print(argv, "rc", rc, "bytes", len(out))
    assert rc == 0 and out.strip()

# demo：使用内置 6 阶段模板 + 20 文件
ns = parser.parse_args(["flow", "demo", "--files", "20"])
buf = io.StringIO()
with redirect_stdout(buf):
    rc = cli.run(ns)
out = buf.getvalue()
print("demo rc", rc, "bytes", len(out))
report = json.loads(out)
print("demo done", report["done"], "trace", report["trace"],
      "batches", report.get("batches", {}).get("transform", {}).get("done_batches"))
assert report["done"] is True
print("OK")
