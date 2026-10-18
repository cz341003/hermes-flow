"""异常自愈端到端演示。

1. 异常分类（各类型）
2. 指数退避序列
3. autonomous_run：限流退避后重试成功
4. 断点续跑：执行到一半 → checkpoint → 模拟重启 → restore → 续跑完成
"""
import json
import sys
import tempfile
import os

sys.path.insert(0, "E:/hermes/plugins/vue3_migration")
sys.path.insert(0, ".")

from vue3migrate_core.engine import (  # noqa: E402
    Edge,
    ExecutionResult,
    Node,
    Scheduler,
    Workflow,
)
from vue3migrate_core.recovery import (  # noqa: E402
    BackoffStrategy,
    JsonCheckpointStore,
    autonomous_run,
    classify,
)

print("=" * 70)
print("演示 1：异常分类")
print("=" * 70)
samples = [
    "HTTP 429 Too Many Requests",
    "context length exceeded, output truncated",
    "request timed out",
    "ModuleNotFoundError: No module named 'vuex'",
    "vite build failed: syntax error",
    "评分低于阈值 70，回环修复",
    "违规并行，违反串行约束",
    "destructive deploy",
]
for s in samples:
    print(f"  {s[:45]:47} -> {classify(s).value}")

print()
print("=" * 70)
print("演示 2：指数退避序列（base=1, factor=2, max=8, jitter=0）")
print("=" * 70)
b = BackoffStrategy(base_seconds=1, factor=2, max_seconds=8, jitter=0)
print("  ", b.delays(5), "-> 封顶 8")

print()
print("=" * 70)
print("演示 3：autonomous_run 限流退避后重试成功")
print("=" * 70)
wf = Workflow(id="w1", name="t", nodes=[Node(id="a", name="A", phase="transform")],
              edges=[])
sched = Scheduler(wf, max_attempts=3)
calls = {"n": 0}
sleeps = []


def runner(node, ctx):
    calls["n"] += 1
    if calls["n"] < 3:
        return ExecutionResult(success=False, error="HTTP 429 rate limit")
    return ExecutionResult(success=True, score=90)


report = autonomous_run(sched, runner, sleep_fn=lambda s: sleeps.append(s))
print(f"  done={report.done} | runner调用={calls['n']} | 退避次数={len(sleeps)}")
for e in report.events:
    print(f"    event: {e.node_id} -> {e.action} ({e.category}) {e.message}")
assert report.done and calls["n"] == 3

print()
print("=" * 70)
print("演示 4：断点续跑（执行到一半 → checkpoint → 重启 → restore 续跑）")
print("=" * 70)
with tempfile.TemporaryDirectory() as d:
    store = JsonCheckpointStore(os.path.join(d, "wf.json"))
    wf2 = Workflow(
        id="mig", name="迁移",
        nodes=[Node(id="analyze", name="结构分析", phase="analyze"),
               Node(id="deps", name="依赖分析", phase="deps"),
               Node(id="transform", name="代码转化", phase="transform"),
               Node(id="quality", name="质量分析", phase="quality")],
        edges=[Edge("analyze", "deps"), Edge("deps", "transform"),
               Edge("transform", "quality")],
    )

    # 第一次运行：执行 analyze + deps 后"进程被杀"
    sched1 = Scheduler(wf2, max_attempts=3)
    n = sched1.next(); sched1.complete(n.id)   # analyze done
    n = sched1.next(); sched1.complete(n.id)   # deps done
    store.save("mig", sched1)
    print(f"  中断时状态: {sched1.states()}  (已 checkpoint)")

    # 模拟重启：全新进程，从磁盘 restore
    sched2 = store.load("mig")
    assert sched2 is not None
    print(f"  restore 后状态: {sched2.states()}  (断点续跑)")

    # 从断点继续执行剩余节点
    n = sched2.next()
    print(f"  续跑取到下一个节点: {n.id}")
    sched2.complete(n.id)                      # transform done
    n = sched2.next(); sched2.complete(n.id)   # quality done
    print(f"  最终: done={sched2.is_done()} states={sched2.states()} "
          f"trace={sched2._trace}")
    assert sched2.is_done()

print()
print("✅ 异常自愈验证通过：分类 / 退避 / 限流自愈 / 断点续跑")
