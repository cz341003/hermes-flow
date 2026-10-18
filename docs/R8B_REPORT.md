# R8b 真实并行采样 + kill/restart 演练报告

- 日期：2026-10-18
- 内容：真实子代理 6 文件并行采样；真实进程 kill → 租约/锁过期 → 重启恢复
- 证据：[r8b-kill-restart.json](r8b-kill-restart.json)

## 1. 真实 6 文件并行采样

- 项目：`E:\deepSeek\plugin\r8b-real`（A–F 6 个 Vue2 Options API 文件）
- Run：`run-20261018-171118-1158`，group `g-06091d475a`
- 策略：2 文件/批，3 批，`concurrency=3`，真实 `ctx.subagent_lifecycle`
- 结果：**3/3 批 done、6/6 applied、全部 pass（97.0–97.6）**

批次时间（来自 batches.db）：

| 批次 | started_at | ended_at | 耗时 |
|---|---|---|---|
| b0001 | 1792314752 | 1792314831 | 79s |
| b0002 | 1792314752 | 1792314831 | 79s |
| b0003 | 1792314752 | 1792314831 | 79s |

三批**同时在 79s 完成**，证明真实 lifecycle 并行生效（不是伪并发）。

**本次修复的真实 bug**：
- `ThreadPoolExecutor` 默认不继承 Hermes 的 parent-session `contextvar`；
  并行 worker 调 `subagent_lifecycle.launch()` 报 `No active Hermes parent session`。
- 修复：为每个 worker 执行 `contextvars.copy_context()`，再 `ctx.run(self._execute, ...)`。
- 修复后真实并行成功。

## 2. kill/restart 真实进程演练

流程：

1. 8 文件 / 2 批；worker 进程 claim 第一批后进入 `launch` 阻塞（模拟长时间子代理）。
2. 父进程确认有 `running` 批次后 **kill worker 进程**。
3. 等租约（2s）与 driver 文件锁（3s）过期。
4. 启动新 worker：同一 DB/queue/group，重新认领过期批次并完成。

结果：

```json
{
  "recover_exit": 0,
  "done_batches": 2,
  "total_batches": 2,
  "failed": [],
  "files": 8,
  "all_v3": true,
  "events": [
    {"batch_id":"b0001","attempt":2,"action":"done","score":97.6,"files_done":4},
    {"batch_id":"b0002","attempt":1,"action":"done","score":97.6,"files_done":4}
  ]
}
```

- 被杀批次以 **attempt=2** 恢复（说明租约过期重认领生效）；
- 8/8 文件最终为 `<script setup>`，无丢失/重复写；
- 新进程成功接收旧进程遗留状态，不依赖内存。

## 3. 1000 文件真实 LLM 成本估算

按本次真实采样：

- 6 文件 / 3 批 / concurrency=3 → **79s wall**；
- 近似每文件 wall ≈ **13.2s**；
- 1000 文件按相同模型/并发粗估 ≈ **3.5–4 小时 wall**（500 批 / 3 并发 × 79s ≈ 3.66h），不含重试/429/质量修复；
- token 成本无法从 lifecycle 结果精确获得（`usage_metadata` 只暴露 api_calls，不含 token 明细），需用 provider 账单核算。

**诚实声明**：本次没有跑真实 1000 文件 LLM（成本/时间不可控），只做了真实 6 文件并行采样 + 1000 文件调度规划（R8）。1000 真实迁移需单独预算与时间窗口。

## 4. 验证

| 项 | 结果 |
|---|---|
| 真实 6 文件 3 批并发 | ✅ 3/3、6/6 applied、pass |
| 并行 wall time | ✅ 79s（三批同时） |
| kill 后 attempt=2 恢复 | ✅ 2/2 批、8/8 文件 v3 |
| 无重复写/丢失 | ✅ applied items 完整 |
| 全量单测 | 75/75（含并行测试） |
| `hermes plugins doctor` | 34 tools / 1 hook |

## 5. 结论

- **kill/restart 真实进程演练达标**：租约过期 + 文件锁过期后新进程可恢复。
- **真实并行达标**：6 文件 3 批在 79s 内全部完成，且修复了 contextvar 传递 bug。
- **1000 文件真实 LLM 迁移仍为预算项**，不是代码阻塞；调度层已由 R8 证明可规划/可推进。
