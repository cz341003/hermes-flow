# R7 同 wave 并行 + worktree 隔离报告

- 日期：2026-10-18
- 代码：[flow_core/batch/driver.py](../plugin/hermes_flow/flow_core/batch/driver.py)、[store.py](../plugin/hermes_flow/flow_core/batch/store.py)、[queue.py](../plugin/hermes_flow/flow_core/batch/queue.py)
- 测试：[tests/test_parallel.py](../plugin/hermes_flow/tests/test_parallel.py)
- 指标：[docs/r7-metrics.json](r7-metrics.json)

## 1. 机制

1. **并发认领**：`BatchStore.claim_next(max_concurrent=N)` 允许同一最早 wave 内最多 N 个 running；跨 wave 仍强制串行。
2. **driver 并发**：`BatchAutoDriver(concurrency=N)`（工具 `flow_batch_auto(concurrency=2|3)`）一次认领同 wave 的 1–3 批。
3. **worktree 隔离**：并行批次把批内源文件复制到
   `plugin-data/hermes_flow/worktrees/<group>/<batch>/src/...`；
   子代理的 `source_path` 指向 worktree，`staging_path` 仍为该批独立目录，不写工作区。
4. **稳定提交**：子代理并跑完成后，按 batch `(wave, seq)` 顺序**串行**执行
   `ingest → apply → audit → gate → complete/repair`；apply 与审计不会并发。
5. **限制**：concurrency 硬上限 3；跨 wave 永远串行；单 driver 文件锁仍然生效。

## 2. 指标

```json
{
  "serial":   { "batches": 3, "max_active": 1, "elapsed_seconds": 0.552, "stable_order": true, "worktree_files": 0 },
  "parallel": { "batches": 3, "max_active": 3, "elapsed_seconds": 0.235, "stable_order": true, "worktree_files": 9 }
}
```

- 9 文件 / 3 批：串行 0.552s；并发 3 批 **0.235s**（约 2.3× 加速，fake launcher 固定 0.15s 延迟）。
- `max_active=3` 证明真实重叠（不是伪并发）。
- `worktree_files=9`：每批 3 个源文件都被复制到独立 worktree。
- `stable_order=true`：提交事件按 batch seq 升序。

## 3. 验证

| 项 | 结果 |
|---|---|
| 同 wave 3 批并发 | ✅ max_active=3 |
| 跨 wave 串行 | ✅ 认领只取最早 wave |
| worktree 隔离 | ✅ 子代理 source_path 在 worktrees 下 |
| 稳定提交顺序 | ✅ seq 升序 |
| 文件全部 apply | ✅ 9/9 |
| 全量单测 | **75/75** |
| 前序 legacy | **123/123** |

## 4. 真实 lifecycle 并行采样（补充）

- 项目：`r8b-real`，6 文件 / 3 批 / concurrency=3；
- 结果：**3/3 done、6/6 applied、全部 pass（97.0–97.6）**；
- 三批 started_at 相同、ended_at 相同（79s），真实并行生效；
- 期间修复：`ThreadPoolExecutor` worker 不继承 Hermes parent contextvar，导致 `No active Hermes parent session`；通过每 worker `contextvars.copy_context()` 修复。

## 5. 边界

- 并行仅批内文件复制到 worktree；如果子代理需要读取批外 import 文件，worktree 中可能缺失（当前 prompt 只要求改批内文件；跨文件依赖应放进同一批或依赖分析阶段补齐）。
- 真实 LLM 并发受 `ctx.subagent_lifecycle` 进程内 8 并发上限约束；driver 上限 3，留出余量。
- apply/audit 串行，文件多时提交阶段仍是串行开销。
- 未做 git worktree/分支级隔离；当前是文件级隔离目录。
