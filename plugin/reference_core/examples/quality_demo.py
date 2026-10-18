"""质量门控端到端演示。

场景：Vue2→Vue3 迁移中，`transform` 节点产出后由质量门打分：
- 高分(>=85) 直接通过
- 70~85 通过但有警告
- <70 自动回环修复，最多 3 轮，超限升级人工门（FAILED）

演示 1：gated_runner 接入 Scheduler（低分回环 → 修复通过）
演示 2：quality_score 纯评分
演示 3：quality_gate 门判定（各档位）
"""
import json
import sys

sys.path.insert(0, "E:/hermes/plugins/vue3_migration")
sys.path.insert(0, ".")

from vue3migrate_core.engine import (  # noqa: E402
    Edge,
    ExecutionResult,
    Node,
    Scheduler,
    Workflow,
)
from vue3migrate_core.quality import (  # noqa: E402
    QualityGate,
    SignalResult,
    Verdict,
    compute_score,
    gated_runner,
)

print("=" * 70)
print("演示 1：gated_runner 接入调度器（低分回环 → 修复通过）")
print("=" * 70)

# transform -> quality 两个节点，串行
wf = Workflow(
    id="demo", name="迁移质量门演示",
    nodes=[
        Node(id="transform", name="代码转化", phase="transform",
             agent="代码转化专家", skill="vue3-transform"),
        Node(id="quality", name="质量分析", phase="quality",
             agent="质量分析专家", skill="vue3-quality"),
    ],
    edges=[Edge("transform", "quality")],
)

# 模拟：transform 先产出低分(60)，修复后高分(92)；quality 恒定高分
transform_scores = iter([60, 92])


def runner(node, ctx):
    if node.id == "transform":
        return ExecutionResult(success=True, score=next(transform_scores))
    return ExecutionResult(success=True, score=95)


sched = Scheduler(wf, max_attempts=3)
report = sched.run(gated_runner(runner))
print(f"done={report.done} | trace={report.trace} | "
      f"failed={report.failed_nodes} | states={report.states}")
assert report.done, "应完成"
assert report.trace == ["transform", "transform", "quality"], report.trace

print()
print("=" * 70)
print("演示 2：quality_score 纯评分（5 信号加权）")
print("=" * 70)
signals = [
    SignalResult("ast", 1.0, "compiler-sfc 解析通过"),
    SignalResult("build", 1.0, "vite build 成功"),
    SignalResult("types", 1.0, "vue-tsc 0 error"),
    SignalResult("browser", 0.0, "渲染报错: ztree API 未定义"),
    SignalResult("behavior", 1.0, "语义一致"),
]
score = compute_score(signals)
print(json.dumps(score.to_dict(), ensure_ascii=False, indent=2))
assert score.score == 75.0

print()
print("=" * 70)
print("演示 3：quality_gate 门判定（各档位）")
print("=" * 70)
gate = QualityGate()
for s in [95, 80, 60, 60, 60, 60]:
    d = gate.evaluate(s, loop_count=0 if s >= 70 else None or 0)
# 上面只是展示门档位，下面用 tracker 展示回环计数
from vue3migrate_core.quality import GateTracker  # noqa: E402

tracker = GateTracker()
subject = "transform:App.vue"
for s in [60, 62, 66, 68]:
    d = tracker.submit(subject, s)
    print(f"  score={s:>2} -> verdict={d.verdict.value:6} "
          f"loop={d.loop_count} | {d.message}")
# 最后一档是 MANUAL
assert d.verdict is Verdict.MANUAL

print()
print("✅ 质量门控闭环验证通过：低分回环 → 超限人工门 → 修复后通过")
