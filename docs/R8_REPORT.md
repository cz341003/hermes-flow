# R8 压测 / 故障注入报告

- 日期：2026-10-18
- 测试：[tests/test_stress.py](../plugin/hermes_flow/tests/test_stress.py)
- 指标：[docs/r8-metrics.json](r8-metrics.json)

## 1. 指标

```json
{
  "plan_1000": { "files": 1000, "batches": 150, "waves": 50, "covered": 1000 },
  "stress": {
    "batches": 100,
    "done": 100,
    "failed": 0,
    "launches": 110,
    "injected": 10,
    "elapsed_seconds": 3.951,
    "done_flag": true
  }
}
```

- **1000 文件**：依赖链每 50 文件一条，规划出 **150 批 / 50 wave**，覆盖率 1000/1000。
- **100 批 + 10 次故障**：700 文件按 7 文件/批 → 100 批；每个故障批次首次返回瞬时失败，driver 自动重试。最终 **100/100 done、failed=0、110 次 launch（10 次重试）**，耗时 **3.95s**（fake lifecycle，不含 LLM 时间）。
- 每批 staging 文件均 apply 到工作区，700 个文件全部存在。

## 2. 覆盖场景

| 场景 | 结果 |
|---|---|
| 1000 文件拓扑规划无遗漏 | ✅ 150 批/50 wave/1000 covered |
| 100 批连续推进 | ✅ 100/100 |
| 10 次瞬时失败自动重试 | ✅ 110 launch = 100 成功 + 10 重试 |
| 重试不重复写文件 | ✅ 700 个文件，批次 item 状态一致 |
| 单次 driver 时间预算 | ✅ max_seconds=300 内完成；实际 3.95s |
| `done` 标志 | ✅ true |

## 3. 边界（诚实声明）

- 压测使用 **fake lifecycle launcher**，验证的是 driver/队列/重试/apply 协议，不含真实 LLM 时延与真实 1000 文件 token 成本。
- `kill/restart` 由租约/持久化单测覆盖（`test_batch` / `test_driver` 的租约过期重认领），尚未在 100 批压测中真实杀进程重启。
- 1000 文件真实迁移仍需 R2 类似的真实子代理跑批（成本/时间高），当前只验证规划与调度上界。
- 100 批耗时是调度开销；真实 LLM 批耗时会在分钟级，需依赖 R1 的断点/重试。

## 4. 结论

R8 的**调度上界与故障注入**已达标：1000 文件可规划、100 批可连续推进、10 次故障可自动恢复、无失败批次。剩余是真实 1000 文件 LLM 成本验证与 kill/restart 演练。
