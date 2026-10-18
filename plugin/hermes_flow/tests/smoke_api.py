"""Dashboard API 冒烟：用 FastAPI TestClient 验证路由与注册中心返回。"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

api = importlib.import_module("hermes_flow.dashboard.plugin_api")
app = FastAPI()
app.include_router(api.router, prefix="/api/plugins/hermes_flow")
client = TestClient(app)

r = client.get("/api/plugins/hermes_flow/status")
print("status", r.status_code, {k: r.json().get(k) for k in ("ok", "agents", "skills", "workflows")})
assert r.status_code == 200 and r.json()["ok"]
r = client.get("/api/plugins/hermes_flow/agents")
print("agents", r.status_code, len(r.json().get("agents", [])))
assert r.status_code == 200 and len(r.json()["agents"]) >= 8
r = client.get("/api/plugins/hermes_flow/workflows")
print("workflows", r.status_code, len(r.json().get("workflows", [])))
print("OK")
