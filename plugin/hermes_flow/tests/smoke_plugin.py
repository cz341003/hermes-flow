"""插件注册冒烟：用 fake ctx 验证 register/工具/CLI 不依赖 Hermes 运行时。"""
import json
import os
import sys
import tempfile

PLUGIN_PARENT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PLUGIN_PARENT)
os.environ["HERMES_HOME"] = tempfile.mkdtemp(dir=os.environ.get("FLOW_TEST_TMP") or tempfile.gettempdir())

import hermes_flow  # noqa: E402


class FakeCtx:
    def __init__(self):
        self.tools = {}
        self.hooks = {}
        self.cli = []
        self.commands = {}

    def register_tool(self, name, toolset=None, schema=None, handler=None, **kw):
        self.tools[name] = {"schema": schema, "handler": handler}

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def register_cli_command(self, name, help=None, setup_fn=None, handler_fn=None, **kw):
        self.cli.append(name)

    def register_command(self, name, handler=None, description="", args_hint="", **kw):
        self.commands[name] = {"handler": handler, "description": description}


ctx = FakeCtx()
hermes_flow.register(ctx)
print("tools", len(ctx.tools), "hooks", list(ctx.hooks), "cli", ctx.cli,
      "commands", list(ctx.commands))
assert len(ctx.tools) >= 25
assert "flow_batch_plan" in ctx.tools
assert "flow" in ctx.commands
r = json.loads(ctx.tools["flow_agent_list"]["handler"]({}))
print("agent_list", r)
r = json.loads(ctx.tools["flow_workflow_list"]["handler"]({}))
print("workflow_list", r["data"]["count"] if r.get("ok") else r)
slash = ctx.commands["flow"]["handler"]("/flow status")
print("slash_status", slash.splitlines()[0] if slash else slash)
assert "HERMES Flow" in slash
print("OK")
