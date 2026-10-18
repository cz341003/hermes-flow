"""委派演示：模拟 Hermes 加载插件，驱动 workflow_create → delegate → complete 串行循环。

验证三点：
1. workflow_create 创建 DAG 并拓扑校验。
2. workflow_delegate 认领下一节点并返回 delegate_task 载荷（绑定角色 + 技能）。
3. 串行硬约束：当前节点 running 时二次 delegate 被拒绝（返回 task=None）。

用法：python examples/delegate_demo.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types

PLUGIN_DIR = "E:/hermes/plugins/vue3_migration"


def load_plugin():
    # 模拟 Hermes 的插件命名空间：父包 hermes_plugins + 插件模块（相对 import 依赖它）
    if "hermes_plugins" not in sys.modules:
        ns = types.ModuleType("hermes_plugins")
        ns.__path__ = []
        ns.__package__ = "hermes_plugins"
        sys.modules["hermes_plugins"] = ns
    spec = importlib.util.spec_from_file_location(
        "hermes_plugins.vue3_migration",
        PLUGIN_DIR + "/__init__.py",
        submodule_search_locations=[PLUGIN_DIR],
    )
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [PLUGIN_DIR]
    module.__package__ = "hermes_plugins.vue3_migration"
    sys.modules["hermes_plugins.vue3_migration"] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    m = load_plugin()

    definition = {
        "id": "demo",
        "name": "演示流程",
        "nodes": [
            {"id": "analyze", "name": "结构分析", "phase": "analyze",
             "agent": "结构分析专家", "skill": "vue3-analyze"},
            {"id": "transform", "name": "代码转化", "phase": "transform",
             "agent": "代码转化专家", "skill": "vue3-transform"},
            {"id": "quality", "name": "质量分析", "phase": "quality",
             "agent": "质量分析专家", "skill": "vue3-quality"},
        ],
        "edges": [
            {"source": "analyze", "target": "transform"},
            {"source": "transform", "target": "quality"},
        ],
    }
    r = json.loads(m.handle_workflow_create({"definition": json.dumps(definition)}))
    assert r["ok"], r
    print("1) workflow_create:", r["workflow_id"], "topo =", r["topo_order"])

    trace = []
    for _ in range(len(definition["nodes"])):
        d = json.loads(m.handle_workflow_delegate({"workflow_id": "demo"}))
        if d.get("task") is None:
            print("   delegate:", d["reason"])
            break
        node_id = d["node_id"]
        trace.append(node_id)
        print(f"2) delegate node={node_id} | goal = {d['task']['goal']}")
        # 串行硬约束：当前节点 running，二次 delegate 应被拒
        d2 = json.loads(m.handle_workflow_delegate({"workflow_id": "demo"}))
        assert d2.get("task") is None, "串行硬约束被破坏！"
        print(f"   -> 二次 delegate 被拒: {d2['reason']}")
        c = json.loads(m.handle_workflow_complete(
            {"workflow_id": "demo", "node_id": node_id}))
        print(f"   -> complete 后 states = {c['states']}")

    s = json.loads(m.handle_workflow_status({"workflow_id": "demo"}))
    print(f"3) 最终: done = {s['done']} | 串行 trace = {trace}")
    assert s["done"], "流程未完成"
    assert trace == ["analyze", "transform", "quality"], "串行顺序错误"
    print("=== 委派演示通过：串行硬约束 + 角色技能绑定 均正确 ===")


if __name__ == "__main__":
    main()
