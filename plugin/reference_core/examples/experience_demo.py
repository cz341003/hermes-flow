"""经验沉淀 + 看板端到端演示。

1. 经验沉淀（record + 去重命中计数）
2. 相似检索回灌（recall，关键词加权排序）
3. 看板渲染（workflow 状态 + 经验 → HTML）
"""
import os
import sys

sys.path.insert(0, "E:/hermes/plugins/vue3_migration")
sys.path.insert(0, ".")

from vue3migrate_core.experience import ExperienceBase  # noqa: E402
from vue3migrate_core.board import render_board  # noqa: E402

print("=" * 70)
print("演示 1：经验沉淀 + 去重命中计数")
print("=" * 70)
exp = ExperienceBase()  # 内存库
e1 = exp.record("transform", "Vue2 filters 被移除", "改用 computed 属性", "vue2.7→vue3.4")
e2 = exp.record("transform", "Vue2 filters 被移除", "改用 computed 属性", "vue2.7→vue3.4")
print(f"  首次沉淀: id={e1.id} times_hit={e1.times_hit}")
print(f"  重复沉淀: id={e2.id} times_hit={e2.times_hit}  (去重，命中 +1)")
assert e2.id == e1.id and e2.times_hit == 2
assert len(exp.search(category="transform")) == 1

exp.record("transform", "v-model 语义变化", "自定义组件改用 modelValue/update:modelValue")
exp.record("deps", "Vuex 依赖缺失", "迁移到 Pinia 并更新 import")
exp.record("quality", "浏览器渲染报错", "检查 ztree→a-tree 兼容")

print()
print("=" * 70)
print("演示 2：相似检索回灌（recall）")
print("=" * 70)
results = exp.recall(phase="transform", context="组件里用了 filters 过滤器")
print("  recall(transform, '组件里用了 filters 过滤器'):")
for r in results:
    print(f"    [{r.category}] {r.trigger} -> {r.solution} (命中 {r.times_hit})")
assert results and "filters" in results[0].trigger.lower()

print()
print("=" * 70)
print("演示 3：看板渲染 → HTML")
print("=" * 70)
workflows = [{
    "id": "mig", "name": "Vue2→Vue3 批量迁移", "done": False,
    "nodes": [
        {"id": "analyze", "name": "结构分析", "phase": "analyze",
         "agent": "结构分析专家", "status": "done", "score": 95},
        {"id": "deps", "name": "依赖分析", "phase": "deps",
         "agent": "依赖分析专家", "status": "done", "score": 90},
        {"id": "transform", "name": "代码转化", "phase": "transform",
         "agent": "代码转化专家", "status": "running", "attempts": 1},
        {"id": "quality", "name": "质量分析", "phase": "quality",
         "agent": "质量分析专家", "status": "ready"},
        {"id": "verify", "name": "浏览器验证", "phase": "verify",
         "agent": "浏览器验证专家", "status": "ready"},
        {"id": "fix", "name": "修复", "phase": "fix", "agent": "修复专家",
         "status": "ready"},
    ],
    "trace": ["analyze", "deps", "transform"],
}]
experiences = [
    {"category": "transform", "trigger": "Vue2 filters 被移除",
     "solution": "改用 computed 属性", "times_hit": 2},
    {"category": "transform", "trigger": "v-model 语义变化",
     "solution": "自定义组件改用 modelValue", "times_hit": 1},
    {"category": "deps", "trigger": "Vuex 依赖缺失",
     "solution": "迁移到 Pinia 并更新 import", "times_hit": 1},
]
html = render_board(workflows, experiences, title="Vue3 迁移控制面看板")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"  看板已生成: {out}")
print(f"  HTML 大小: {len(html)} 字节")

print()
print("✅ 经验沉淀 + 看板验证通过：去重沉淀 / 关键词回灌 / 看板渲染")
