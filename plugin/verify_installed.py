"""验证 E:\\hermes\\plugins\\hermes_flow 安装副本：注册、API、CLI demo、Dashboard 资产。"""
import argparse
import importlib
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, r"E:\hermes\plugins")
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=r"E:\deepSeek\plugin\.tmp")

import hermes_flow  # noqa: E402

PLUGIN = r"E:\hermes\plugins\hermes_flow"


class FakeCtx:
    def __init__(self):
        self.tools, self.hooks, self.cli = {}, {}, []

    def register_tool(self, name, **kw):
        self.tools[name] = kw

    def register_hook(self, name, cb):
        self.hooks[name] = cb

    def register_cli_command(self, name, **kw):
        self.cli.append(name)


ctx = FakeCtx()
hermes_flow.register(ctx)
print("installed tools", len(ctx.tools), "hooks", list(ctx.hooks), "cli", ctx.cli)
assert len(ctx.tools) == 31 and ctx.hooks and ctx.cli

# API（需要 fastapi，由调用方通过 PYTHONPATH 提供）
from fastapi import FastAPI
from fastapi.testclient import TestClient

api = importlib.import_module("hermes_flow.dashboard.plugin_api")
app = FastAPI()
app.include_router(api.router, prefix="/api/plugins/hermes_flow")
client = TestClient(app)
status = client.get("/api/plugins/hermes_flow/status")
print("api status", status.status_code, {k: status.json().get(k) for k in ("agents", "skills", "workflows")})
assert status.status_code == 200
assert status.json()["agents"] == 8 and status.json()["skills"] == 12
assert status.json()["workflows"] == 2

# CLI demo（287 文件，验证内核对大批量）
from hermes_flow import cli

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="root")
flow = sub.add_parser("flow")
cli.setup(flow)
ns = parser.parse_args(["flow", "demo", "--files", "287"])
buf = io.StringIO()
with redirect_stdout(buf):
    rc = cli.run(ns)
report = json.loads(buf.getvalue())
print("demo rc", rc, "done", report["done"],
      "batches", report.get("batches", {}).get("transform", {}).get("done_batches"),
      "/", report.get("batches", {}).get("transform", {}).get("total_batches"))
assert rc == 0 and report["done"] is True

# Dashboard 资产
for rel in ("dashboard/manifest.json", "dashboard/dist/index.js", "dashboard/dist/style.css"):
    path = os.path.join(PLUGIN, rel)
    assert os.path.getsize(path) > 100, rel
print("dashboard assets OK")
print("INSTALLED VERIFY OK")
