# 批量拆分 + 子代理循环：调研与设计分析

> 需求补充：大型 Vue2 项目文件多，需要把待转化文件拆成多个批次，**每个批次作为一个子任务**交给子代理完成；插件应支持"某个子代理循环完成一批任务"的编排能力。
> 调研时间：2026-10-18　|　宿主：Hermes Agent v0.22.2（`E:\hermes`，commit `d923a5e`）
> 结论文件：本文件；落地章节：`docs/PRD.md` FR-10 / §8.4 / §9.4 / §14.6 / 附录 G
> 证据分级：✅ 本机源码/日志原文（`文件:行号`）；📄 官方文档原文；🧠 设计推导

---

## 0. 结论

**可实现，且 Hermes 已提供两种互补的批量执行通道，不需要改核心。**

- **通道 A：`delegate_task(tasks=[...])` 批量委派**——一次调用最多 10 个并行子代理（可配置、无硬上限），线程池执行、结果按输入顺序返回、后台完成事件持久化；**批次超过并发上限会直接报错而不是自动排队**，因此插件必须自己切"波次"。子代理摘要受 **24,000 字符硬上限**（`delegate_tool_results.py:160`，可配且受父上下文 headroom 影响）。
- **通道 B：`ctx.subagent_lifecycle` 生命周期子代理**——插件在活跃 agent turn 内自行 `launch/wait/cancel`，进程内线程池 **max_workers=8**，支持每批指定 `model/provider/allowed_toolsets/correlation_id`，result/context ≤32,000 字符；**不支持单次 timeout**，需插件自己 `wait(timeout)+cancel`；**不支持 `output_schema`**（`structured_payload` 仅声明未实现），结构化结果需"提示词约束 + 插件侧 JSON 校验 + 一次格式纠正重派"。
- **推荐架构：外层批次循环（插件）+ 中层波次并发（可选）+ 内层文件循环（子代理）**：
  - 插件把文件依赖图切成**拓扑有序的批次队列**（Batch Queue）；每批 = 一个子任务 = 一个 Batch Packet；
  - 默认**波次串行**（第 N 批完成才启动 N+1），保证依赖安全与失败隔离；
  - 可选"同层并行"（仅当依赖图证明互不依赖时，并发 ≤3；并行批必须使用独立 worktree/staging 目录）；
  - 子代理在批内按拓扑序循环处理文件（`inner_loop=serial`），**只写 staging 目录**，返回逐文件结果（JSON；插件校验后原子应用）；
  - 每批独立质量门 + 文件级幂等 + 断点续跑；失败只重跑/拆分该批（最多拆 2 层）；
  - 全部批次完成后做一次聚合门（aggregate gate）。
- **写入治理**：子代理不直接改工作区，而是写 `staging/<run>/<batch>/`；插件校验"只含批内文件"后，备份原文件 → 原子应用 → 记录 `applied_hash` 账本。崩溃后按账本续跑，避免"写后崩溃→重复转换"。

**不建议**把整个项目塞给一个"持久循环子代理"（上下文膨胀、单点失败会丢掉全部进度），也不建议依赖 `delegate_task` 的批量自动排队（超限直接报错），更不建议一开始就用 kanban 多进程派发（重、慢、观测复杂）。

**预期效果**：287 文件 → 约 43 批 × 7 文件（示例；实际由上下文预算装箱决定）；单批上下文可控（≤32k 字符）、失败隔离到批、断点精确到文件；吞吐由"批次数 × 单批耗时"决定，默认串行时稳定、可预测，开启同层并行可提升 1.5–2.5×。

---

## 1. 需求拆解：三个层级的"循环"

| 层 | 谁在循环 | 循环对象 | 目的 | 本设计 |
|---|---|---|---|---|
| **L1 外层（控制面）** | 插件调度器 | 批次队列（Batch） | 长周期任务分段推进、失败隔离、断点续跑 | ✅ 默认串行；可配同层并行 |
| **L2 中层（波次）** | 插件/主 Agent | 同一依赖层内的多个批次 | 提升吞吐 | ✅ 可选 `max_concurrent_batches=1..3` |
| **L3 内层（子代理）** | 子代理自身 | 一个批次内的文件/组件 | 减少子代理启动开销、批内保持上下文 | ✅ `inner_loop=serial`（推荐）；或 `single_file`（一批一文件，最稳） |

> 用户原话"让某个子代理循环完成某一批任务，每个批次算一个子任务"对应：**L1 由插件循环派发批次，L3 由子代理循环处理批内文件**。L2 是可选加速项。

### 1.1 为什么必须分批（而不是一个大任务）

| 问题 | 单任务处理 287 文件 | 分批（43 批 × 7 文件） |
|---|---|---|
| 上下文 | 必然超 32k / 溢出压缩，后半段质量衰减 | 每批独立上下文，稳定 |
| 失败影响 | 一次失败/截断 → 整段重来 | 只重跑该批（≤7 文件） |
| 质量门 | 只能整体打分，无法定位 | 每批打分 + 文件级证据 |
| 并发 | 单线程串行 | 可选同层并行 |
| 断点 | 粒度粗 | 文件级 + 批次级 |
| 成本 | 重试成本高 | 重试成本可控 |
| 进度可观测 | "进行中" | 批次 18/43、文件 126/287 |

---

## 2. Hermes 原生批量能力（证据）

### 2.1 `delegate_task` 批量委派（✅/📄）

- 入参：`goal/context` 单任务或 `tasks=[{goal, context, output_schema, role, images, group}]` 批量；`background` 对单任务和批量都生效（`tools/delegate_tool.py:483-513`）。
- 并发：默认 **10** 个并行子代理（`_DEFAULT_MAX_CONCURRENT_CHILDREN = 10`，`tools/delegate_tool_config.py:17`；配置项 `delegation.max_concurrent_children` / `DELEGATION_MAX_CONCURRENT_CHILDREN`，下限 1、无硬上限）。注：宿主 `configuration.md` 有"default 3"的过期示例，以源码与 delegation 文档为准。
- **超限行为**：**批次大于并发上限会返回工具错误，而不是自动排队/截断**（`website/docs/user-guide/features/delegation.md:211`；`tools/delegate_tool_tasks.py:83`）。
- 执行：`ThreadPoolExecutor`；结果按 task index 排序；每个 task 可带独立 `output_schema`（结构化输出校验 + 一次纠正轮）；批量调用是**一个 async unit**，默认等全部完成后返回一条汇总消息；开启 `delegation.independent_completions` 后可按 group 独立返回（`delegation.md:184-215`）。
- 取消：`/stop`/关闭会话会终止整个批次；每个被终止 child 仍返回 `status="interrupted"` 与部分输出（`delegation.md:215`）。
- 完成持久化：后台完成的 completion event 先写 `state.db` 再投递，重启后可恢复投递；**但不会恢复 child 执行**，进程消失的 child 记为 `unknown`（`delegation.md:219-233`）。
- 子代理限制：默认 `leaf`，不能再次委派；`role="orchestrator"` 可嵌套，受 `max_spawn_depth`（默认 1，扁平）限制（`delegation.md:329-360`；`delegate_tool_config.py:21,151-167`；`delegate_tool.py:226-229`）。
- 预算：child 迭代上限默认 **250**（全局 `delegation.max_iterations`，不是 per-call 参数）；**默认无 wall-clock 超时**，靠心跳停滞检测（450s idle / 1200s in-tool）；可选 `child_timeout_seconds` 只约束"无进展"（`delegation.md:342-380`；`delegate_tool_config.py:24-27`；`delegate_tool.py:111-112`）。
- 结果：child **summary 硬上限 24,000 字符**（`delegate_tool_results.py:160,163,166,275-277`），超出会 head/tail 截断并落盘 spill；父上下文 headroom 可能进一步压缩。**32,000 是 lifecycle 的上限，不是 delegate_task 的**。

**对设计的含义**：适合"波次批量"（一次 launch 一批子任务），但插件必须自己控制每波 ≤ 并发上限；且**不能依赖它做崩溃续跑**，必须在批次/文件层做 checkpoint + 幂等。

### 2.2 `ctx.subagent_lifecycle`（✅/📄）

- 插件 API：`launch(SubagentLaunchRequest) -> handle`；`status/wait/cancel/steer/result/reconnect`；状态机 `PENDING→STARTING→RUNNING→SUCCEEDED/FAILED/INTERRUPTED/CANCELLED`（`hermes_cli/plugins.py:386`、`developer-guide/subagent-lifecycle-api.md:15-64`）。
- 请求字段：`goal/context/role/model/provider/allowed_toolsets/blocked_tools/working_directory/parent_session_id/correlation_id/metadata/timeout_seconds`（其中 `timeout_seconds` **被显式拒绝**：`agent/subagent_lifecycle.py:228`）。
- 上限：goal ≤16,000 字符、context ≤32,000 字符、metadata ≤8KB、结果 ≤32,000 字符（`subagent_lifecycle.py:25-28,221-228`）。
- **无 `output_schema`**：请求不接收 schema；`SubagentResult.structured_payload` 仅声明、全仓无赋值（`subagent_lifecycle.py:120`）。结构化结果只能靠"提示词约束 + 插件侧 JSON Schema 校验 + 一次格式纠正重派"。
- 并发：进程内 daemon 线程池 **max_workers=8**（`subagent_lifecycle.py:159-160`）。
- 前提：必须有活跃父会话/agent turn，否则 `No active Hermes parent session`（`:277-280`）；children 仅进程内，进程退出后 `reconnect` 返回 `RECONNECT_UNAVAILABLE`（`:269-272,371-375`）。
- 优点：插件可**逐批**指定 model/toolsets/correlation_id，天然适合"批次 = 子任务"的细粒度治理。

**对设计的含义**：这是批次循环的**首选执行通道**；并发预算按 8 设计（建议默认 1，最多 3，留余量给质量/修复子代理）。

### 2.3 其他可复用通道

| 通道 | 能力 | 适用 | 不适用 |
|---|---|---|---|
| `delegate_task` 批量（主 Agent 调用） | 10 并发、结构化输出、原生进度树、group | 波次并行、需要主 Agent 汇总 | 插件 RPC 直接调（`dispatch_tool` 在 gateway 下 parent_agent 为 None，`plugins.py:674-683` 注释明确） |
| `ctx.subagent_lifecycle` | 8 并发、逐批控制、per-launch model/toolsets | 插件自治循环 | 跨进程恢复；单次 timeout/结构化 schema 不支持 |
| kanban dispatcher | 持久任务板、跨进程 worker、任务依赖、崩溃回收、60s tick | 超大规模/跨会话/多机 | 重、慢、不是"批内循环" |
| `/goal` + cron | 跨 turn 的 Ralph loop、确定性 gate | 无人值守 driver | 不提供子代理并发/批次模型 |
| `delegate_task` background | 单 async unit、完成持久化投递 | 异步长任务 | 崩溃不恢复 child 执行 |

### 2.4 关键约束汇总（设计必须遵守）

1. `delegate_task` 批量 >10（或配置值）直接报错 → 插件必须切波次。
2. `subagent_lifecycle` 并发上限 8 → 批次并发默认 1、上限 3（预留修复/质量子代理）。
3. 两种通道都**不保证进程崩溃后 child 继续执行** → 批次级 checkpoint + 文件级幂等是硬要求。
4. **结果上限不同**：lifecycle 32,000；delegate_task summary 24,000（可配、headroom 影响）→ 批次结果契约按 24k 设计，逐文件结果要紧凑（path/status/hash/notes≤200 字符）。
5. `delegate_task` 子代理不能自定义 toolsets（继承父）；`lifecycle` 可以 `allowed_toolsets` 收窄 → 批次专家建议用 lifecycle 控制工具面。
6. 子代理没有交互能力（`clarify` 被禁）→ 批内遇到需要人判断的情况必须返回 `manual`，由插件生成人工门。
7. `lifecycle` 没有 `output_schema` → 结构化结果必须由插件解析校验；失败一次重派，仍失败转 `single_file`/人工。
8. child 拥有 file/terminal 工具，**无法按路径限制写入** → 必须"只写 staging + 插件对账应用"，不能依赖提示词/白名单。
9. lifecycle handle 仅进程内保留 **1 小时**（`_TERMINAL_RETENTION_SECONDS=3600`），跨进程 `reconnect=RECONNECT_UNAVAILABLE` → 跨 tick/跨进程必须靠租约过期 + staging/哈希对账恢复。
10. 需要 **driver 单例锁**（否则多 cron/driver 会突破并发上限与 wave 串行）；单批 `wait` 必须分片（≤60s）以免阻塞心跳与 tick 预算。

---

## 3. 方案对比

| 方案 | 做法 | 优点 | 缺点 | 判定 |
|---|---|---|---|---|
| **A. 插件批次循环（推荐）** | 插件切批 → 每批 `lifecycle.launch` 一个子代理 → wait/门控 → 下一批 | 控制粒度最细、失败隔离、可 per-batch model/toolsets、与状态内核天然集成 | 插件需管理并发/超时/续跑；串行时吞吐一般 | ✅ 默认 |
| B. 持久循环子代理 | 启动一个子代理，把多批清单全给它，内部循环 | 启动开销小、减少跨批调度 | 上下文膨胀、单点失败丢全部进度、无法逐批门控、迭代 250 上限；**P2 实验能力，需 child 内每批 checkpoint** | ⚠️ P2 实验（默认关闭） |
| C. Orchestrator 子代理 | `role=orchestrator` 子代理，内部再 `delegate_task` 派 leaf | 主 Agent 只面对一个句柄 | 嵌套默认关闭（max_spawn_depth=1）、插件看不到内部批次、错误归因难 | ⚠️ 可选实验 |
| D. `delegate_task` 波次批量 | 主 Agent 一次调用 `tasks=[≤10]`，插件记录结果 | 原生并发/进度/结构化输出 | 要求主 Agent 在环、批次结果一次性返回、插件不能直接调用（gateway） | ✅ 作为加速/降级模式 |
| E. kanban 派发 | 每批一张卡，dispatcher 起 worker | 跨进程/持久/可跨机 | 60s tick、进程重、观测链路长、与"批内循环"不匹配 | ⚠️ P2 规模化选项 |

**推荐组合：A 为主（默认串行、每批一个子代理），D 为可选加速（同层并行），B 仅作为 P2 实验能力（`persistent_child`，需 child 内每批 checkpoint 与独立验收 B15），E 留作后续规模化后端。**

> **"多批循环"口径（与用户确认后收敛）**：P0 支持的是"**插件循环批次（L1）+ 子代理循环批内文件（L3）**"——每个批次一个子任务、一个子代理；一个子代理一次只处理 1 批（`max_batches_per_launch=1`）。"一个子代理连续处理多批"（B）列为 P2 实验，默认关闭。

---

## 4. 批次规划算法

### 4.1 输入与约束

- 输入：文件清单 `files[]`（含依赖 `deps[]`、大小 `size`、风险等级）、项目根、专家策略 `loop_policy`。
- 约束：
  1. **依赖安全**：若 `A` 依赖 `B`，则 `batch(A)` 不得早于 `batch(B)`；同批内子代理必须按拓扑序处理。
  2. **上下文预算**：`sum(estimated_chars(batch)) + prompt_overhead ≤ context_budget_chars`（默认 28,000，留 4k 余量）。
  3. **批大小上下限**：`min_batch_size=1`、`max_batch_size=12`（默认 **7**，实际由预算装箱决定）。
  4. **波次**：同一 wave 内批次互不依赖；跨 wave 串行。
  5. **风险隔离**：高风险文件（router/entry）单独成批、**提前人工复核**；不得"先跑"破坏 wave 顺序。

### 4.2 算法（拓扑分层 + 预算装箱）

```
输入: files, deps_graph, policy
1) topo = topo_sort(files)                     # 复用前序 core 的 topo_order_files（migrator.py:134）
2) level[v] = 1 + max(level[d] for d in deps[v])，无依赖 = 0
3) waves = group_by(level)                     # 同一 wave 内互不依赖
4) for wave in waves:
     pending = wave (按 topo 顺序)
     while pending:
        batch = []
        budget = policy.context_budget_chars - prompt_overhead
        while pending and len(batch) < policy.max_batch_size:
            f = pending[0]
            if estimate_chars(f) > budget and batch: break
            batch.append(f); pending.pop(0); budget -= estimate_chars(f)
        if not batch: batch = [pending.pop(0)]        # 超大文件单独成批
        batches.append(Batch(wave=wave.index, files=batch))
5) 风险标记: 高风险文件 → 单独批次 + priority=high（**提前人工复核，不改变 wave 顺序**）
6) 输出: ordered_batches[]（wave 升序，批内按 topo 序）
```

- `estimate_chars(f)`：`file_size * 1.2 + 2000`（含 prompt/说明开销）；也可用真实 token 估算器（tiktoken 可选）。
- **自适应批大小**：首次按预算切；若某批返回 `truncated=true` 或质量门报"上下文截断"，则**二分拆批**（`split_depth+1`，最多 2 层）；连续成功 3 批可尝试 `batch_size *= 1.2`（上限 12）。
- **批次数量预估**：`ceil(total_chars / (context_budget - overhead))`，再按 `max_batch_size` 修正。示例：287 文件、平均 2KB、预算 28k → 每批约 10 文件 → 29 批；平均 6KB → 每批约 4 文件 → 72 批；默认"7 文件/批 → 43 批"是**示例口径**，实际以预算装箱结果为准。

### 4.3 示例：287 文件

| Wave | 文件数 | 批数（示例 batch_size=7） | 说明 |
|---|---|---|---|
| 0 基础 utils/constants + store 核心 | 38 | 6 | 无依赖/低依赖，可并行（可选）；store 必须在组件之前 |
| 1 components 叶子 | 96 | 14 | 依赖 wave0 |
| 2 业务组件 | 74 | 11 | 依赖 wave1 |
| 3 views/pages | 52 | 8 | 依赖 wave2 |
| 4 router/entry（高风险） | 27 | 4 | 单独批 + 人工复核；其依赖 views 已在前序 wave |
| **合计** | **287** | **43** | 串行约 43 × 单批耗时 |

> 上表为示例；实际批数由预算与文件大小决定（默认 7 文件/批 → 约 43 批）。router/entry 是"最后关键批"，store 必须前置。

---

## 5. 数据模型与状态机

### 5.1 Expert 的循环策略（新增）

```json
{
  "id": "code-transformer",
  "name": "代码转化专家",
  "loop_policy": {
    "enabled": true,
    "mode": "per_batch",              // P0: per_batch | single_file；persistent_child=P2 实验
    "inner_loop": "serial",           // serial（批内按拓扑序循环）| parallel（批内再并发，默认禁）
    "max_files_per_batch": 7,
    "max_batches_per_launch": 1,      // P0 必须=1（每批一个子代理）；>1 仅 P2 实验
    "max_concurrent_batches": 1,      // 默认波次串行；可选 2–3（仅同 wave，需 worktree 隔离）
    "context_budget_chars": 28000,
    "split_on_failure": true,
    "max_split_depth": 2,
    "checkpoint_each_batch": true,
    "quality_gate_per_batch": true,
    "write_mode": "staging_apply",    // 子代理只写 staging，插件校验后原子应用
    "max_files_per_child_result": 12  // 结果按 24k 字符设计（delegate 通道）
  }
}
```

### 5.2 表结构（新增）

```sql
-- 批次组（一次批量节点的运行实例）
CREATE TABLE batch_groups(
  id TEXT PRIMARY KEY, run_id TEXT, node_id TEXT, expert_id TEXT,
  total_files INTEGER, total_batches INTEGER, done_batches INTEGER DEFAULT 0,
  aggregate_score REAL, aggregate_verdict TEXT,
  status TEXT, policy_json TEXT, created_at INTEGER, updated_at INTEGER
);
-- 批次（最小子任务）
CREATE TABLE batches(
  id TEXT PRIMARY KEY, group_id TEXT, wave INTEGER, seq INTEGER,
  status TEXT,            -- planned|ready|running|gated|done|failed|split|skipped
  attempt INTEGER DEFAULT 0, split_depth INTEGER DEFAULT 0,
  files_json TEXT,        -- 计划快照（只读；状态以 batch_items 为准）
  score REAL, verdict TEXT,
  lease_owner TEXT, lease_expires_at INTEGER, version INTEGER DEFAULT 0,
  agent_correlation_id TEXT,  -- lifecycle correlation_id，用于归因/取消
  started_at INTEGER, ended_at INTEGER
);
-- 文件级进度（幂等/唯一事实源）
CREATE TABLE batch_items(
  id TEXT PRIMARY KEY, group_id TEXT, batch_id TEXT, file_path TEXT,
  status TEXT,            -- pending|running|staged|applied|done|failed|manual
  attempt_id TEXT,        -- 当前 attempt（写回只接受它）
  base_hash TEXT,         -- 迁移前内容 hash
  staged_path TEXT,       -- staging 目录路径
  applied_hash TEXT,      -- 应用后内容 hash（续跑对账）
  attempts INTEGER DEFAULT 0, evidence_json TEXT, updated_at INTEGER,
  UNIQUE(group_id, file_path)
);
-- 批次回执（审计/续跑）
CREATE TABLE batch_receipts(
  id TEXT PRIMARY KEY, batch_id TEXT, attempt INTEGER, event TEXT,
  payload_json TEXT, created_at INTEGER,
  UNIQUE(batch_id, attempt, event)
);
```

- 索引：`batches(group_id,status)`、`batch_items(batch_id)`、`batch_items(group_id,status)`、`batch_receipts(batch_id)`。
- **唯一事实源**：`batch_items` 是文件状态真相；`batches.files_json` 只是计划快照。
- **幂等键**：`(group_id, file_path)` 唯一；`applied_hash` 用于续跑对账；写回校验 `attempt_id` 与 `expected_version`。

### 5.3 状态机

```
Batch: planned → ready → running → gated ──pass──▶ done
                    │           │
                    │           ├── warn ──▶ done（记录待办）
                    │           └── rework ──▶ repair（该批失败文件子批）→ gated
                    ├── child_failed ──▶ retry(≤max_attempts) / split（≤2 层）
                    └── lease_expired ──▶ ready（幂等重放）
BatchGroup: planning → running ⇄ paused → aggregating → succeeded | failed | manual
```

- **批内文件状态**独立于批次状态：批内部分成功时，批次可进入 `repair` 只处理失败文件；全部文件 `done` 才 `done`。
- **人工门**：高风险批次或拆分 2 层仍失败 → 人工门；人工可选择"接受当前批次/继续拆分/跳过/终止"。

---

## 6. 执行流程与 Turn Packet

### 6.1 批次循环伪代码（插件侧）

```
def run_batch_group(run, node, expert, files):
    acquire_run_driver_lock(run)                       # 单写者：多 cron/driver 互斥
    if not acquired: return "busy"                     # 另一个 driver 在跑
    plan = build_batches(files, expert.loop_policy)    # 拓扑分层 + 预算装箱
    persist_batches(plan)
    start_heartbeat(run)                               # ctx.spawn_task：30s 续租
    deadline = now() + policy.tick_budget_seconds
    while group.has_work() and now() < deadline:
        batch = group.next_ready()                     # 同 wave 内按 seq
        if group.running_count >= policy.max_concurrent_batches:
            poll_handles(short=5s); continue
        lease = claim(batch, ttl=600)                  # 原子 + TTL
        staging = make_staging_dir(run, batch)          # 子代理只写这里
        packet = build_batch_packet(run, batch, expert, staging)
        handle = ctx.subagent_lifecycle.launch(SubagentLaunchRequest(
            goal=packet.goal, context=packet.context,
            model=expert.model, allowed_toolsets=expert.toolsets,
            working_directory=packet.project_root,   # 读源码；写只允许 staging_path
            correlation_id=f"{run.id}:{batch.id}:{batch.attempt}",
            metadata={"run_id": run.id, "batch_id": batch.id}))
        handles[batch.id] = handle
        # 小步等待，不阻塞心跳/取消；跨 tick 保留 handle（进程内 1h）
        terminal = wait_slices(handle, slice=60s, until=min(deadline, batch_deadline))
        if not terminal:
            persist_handle_ref(batch, handle); continue  # 下个 tick 继续轮询
        result = service.result(handle)
        parsed = parse_and_validate(result, packet.result_contract)  # lifecycle 无 output_schema
        if parsed is None:
            return redispatch_format_repair(batch, result)           # 一次格式纠正；仍失败→single_file
        applied = ingest_and_apply(batch, parsed)      # 白名单 diff → 备份 → staging 原子应用 → applied_hash
        if not applied.ok:
            return fail_or_manual(batch, applied.reason)            # 越界写/应用失败→人工门
        score = gate_batch(batch)                      # 批级：AST/diff/局部类型/LLM（不含全量 build）
        if score.pass: complete(batch)
        elif score.rework: repair(batch, failed_files, score)
        elif result.truncated: split(batch)
        else: fail_or_retry(batch)

    release_handles_kept()                             # 跨 tick handle 保留在内存表
    if driver_idle(): release_run_driver_lock(run)
    aggregate = aggregate_gate(group)                  # 全量 build/type/browser + 覆盖率
    finish_run(group, aggregate)
```

- **driver 单例锁**：DB 行锁/文件锁；每 tick 只有持有者可推进 Run，避免多 cron/多 driver 突破并发与 wave 串行。
- **心跳**：独立 `ctx.spawn_task` 每 30s 续租；`wait` 分片（≤60s）避免阻塞心跳。
- **tick 预算**：`tick_budget_seconds`（默认 600s）与 `max_batches_per_tick` 双约束；到点保留 handle/checkpoint 后干净退出。
- **跨 tick/跨进程**：handle 仅进程内保留 1h；跨进程按 `lease_expires_at` 回收 → 批回 `ready` → 用 `applied_hash/staged_path` 对账，只重跑未应用文件；批次不重复转换已应用文件。
- **driver**：cron 心跳 / `/goal` / 前台会话，三选一；REST handler 只创建 Run 与唤醒 driver（执行契约同 PRD §10.4）。

### 6.2 Batch Turn Packet（≤32,000 字符）

```json
{
  "run_id": "r-20261018-001",
  "node_id": "transform",
  "batch_id": "b-0007",
  "batch_index": 7,
  "batch_total": 43,
  "wave": 2,
  "attempt": 1,
  "goal": "处理第 7 批（7 个文件）的 Vue3 迁移；读取 source_path，只写 staging_path，禁止修改工作区",
  "project_root": "E:\\Project\\admin-platform",
  "staging_root": "E:\\hermes\\plugin-data\\hermes_flow\\staging\\r-20261018-001\\b-0007\\",
  "files": [
    {"path": "src/components/UserTable.vue", "source_path": "E:\\Project\\admin-platform\\src\\components\\UserTable.vue", "staging_path": "E:\\hermes\\plugin-data\\hermes_flow\\staging\\r-20261018-001\\b-0007\\src\\components\\UserTable.vue", "hash": "sha256:…", "risk": "low"},
    {"path": "src/views/UserList.vue", "source_path": "E:\\Project\\admin-platform\\src\\views\\UserList.vue", "staging_path": "E:\\hermes\\plugin-data\\hermes_flow\\staging\\r-20261018-001\\b-0007\\src\\views\\UserList.vue", "hash": "sha256:…", "risk": "high"}
  ],
  "order": ["src/components/UserTable.vue", "src/views/UserList.vue"],
  "write_policy": {"mode": "staging_only", "workspace_baseline": "git_status_diff", "forbidden": ["project_root 下任何非 staging 路径"]},
  "deps_summary": "本批依赖的 UserStore 已在批 3 完成（pinia store 已迁移）",
  "skills": ["vue3-transform", "vuex-to-pinia"],
  "experience": [{"trigger": "antdv scopedSlots", "solution": "改用 #default 插槽"}],
  "constraints": {"style": "prefer <script setup>", "language": "zh-CN"},
  "result_contract": {
    "format": "json",
    "enforced_by": "prompt+plugin_validation",
    "max_chars": 24000,
    "schema": {
      "type": "object",
      "required": ["files", "summary"],
      "properties": {
        "files": {"type": "array", "items": {
          "type": "object",
          "required": ["path", "status", "changes", "notes"],
          "properties": {
            "path": {"type": "string"},
            "status": {"enum": ["done", "failed", "manual"]},
            "changes": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
            "error": {"type": "string"}
          }
        }},
        "summary": {"type": "string"},
        "truncated": {"type": "boolean"}
      }
    }
  },
  "budget": {"max_iterations": 60, "context_chars": 28000, "timeout_s": 1800}
}
```

- **结果契约的两条通道**：`lifecycle` **没有 `output_schema`**——`result_contract` 靠提示词 + 插件 JSON 校验 + 一次格式纠正重派；`delegate_task` 通道有原生 per-task `output_schema`，但 summary 上限 24k（design by 24k）。
- **逐文件结果契约**是批次循环的关键：插件据此写 staging 状态、计算质量分、生成修复子批。
- 批内文件按 `order`（拓扑序）处理；**子代理以 `project_root` 为 cwd 读取 `source_path`，只写 `staging_path`**；插件启动前记录工作区基线，结束后审计 `post - pre - 批内文件`，越界写直接回滚 + `agent_drift` + 人工门。

### 6.3 子代理内层循环（L3）

子代理收到"本批 N 个文件"后，按 `order` 循环：读工作区文件 → 迁移 → 自检（parse/局部）→ **写 staging 副本** → 记录 changes/notes；最后输出 JSON 结果。

- 若 `inner_loop=serial`：子代理自己串行处理，一次 launch 完成整批。
- 若 `mode=single_file`：每批只含 1 文件（最稳，但启动开销 ×N）。
- 若 `persistent_child`（P2 实验）：一个子代理连续处理 ≤3 批，每批结束必须输出 batch checkpoint + 结果；上下文滚动摘要；默认关闭。
- 不建议在批内再开子代理（leaf 不能 delegate；orchestrator 嵌套默认关闭）。
- **写入策略**：child 只写 staging；插件校验 stage 文件集合 ⊆ 批内文件 + 路径合法，然后备份并原子应用，记录 `applied_hash`。

---

## 7. 失败处理与恢复（按批次/文件）

| 异常 | 检测 | 处理 | 粒度 |
|---|---|---|---|
| 429 限流 | 子代理/工具错误 | 暂停当前波次 → 指数退避 → 重新 launch 该批 | 批 |
| 输出截断 | `truncated=true` / finish_reason=length | 二分拆批（split_depth+1）后重跑；仍截断 → single_file | 批 → 文件 |
| 上下文超限 | 估算/实际溢出 | 拆批；`batch_size` 下调 20% | 批 |
| 子代理超时/停滞 | `wait` 分片 + 心跳 450s/1200s | `cancel()` → 重试（可选降级模型）→ 拆批 | 批 |
| 子代理崩溃/进程退出 | handle `UNKNOWN` / 进程重启 | 租约过期 → 批回 `ready`；按 `applied_hash/staged_path` 对账，只重跑未应用文件 | 批 + 文件 |
| **handle 丢失**（跨进程/超 1h） | status 不可用 / 进程变更 | 租约过期 → `ready` → 对账（applied_hash）→ 重派未应用文件 | 批 + 文件 |
| **结果 JSON 解析失败** | 解析/schema 校验失败 | 一次格式纠正重派；仍失败 → single_file 或人工门 | 批 |
| **越界写** | staging 文件集合 ⊄ 批内文件、路径非法 | 拒绝 apply + 回滚 staging；判 `agent_drift`；人工门 | 批 |
| **apply 失败/崩溃窗口** | 备份/原子替换失败；apply 后未记账 | staging 保留 + 备份回滚；applied_hash 对账，已应用文件跳过 | 文件 |
| 部分文件失败 | 逐文件结果 `failed` | 生成 repair 子批（只含失败文件），最多 3 轮 | 文件 → 批 |
| 质量低分 | 批次评分 < 阈值 | repair 子批（带低分证据/经验）；3 轮后人工门 | 批 |
| 文件被外部修改 | 读时 hash 与计划不一致 | 标 `manual`/`stale`，不覆盖；人工或重新分析 | 文件 |
| 全部批次完成但聚合门失败 | 聚合评分/覆盖率不足 | 定位低分批次 → repair；仍失败 → 人工门 | 组 |

**写入治理（staging-only + 工作区审计）**：
1. **Packet 提供绝对路径**：`project_root`（只读源）、`staging_root`（可写）、每文件 `source_path/staging_path`；child cwd=project_root。
2. **启动前基线**：记录 `git status --porcelain` + `git diff --name-only`（或 hash 快照）到 `batches.workspace_baseline_json`。
3. **结束后审计**：`post - pre - 批内文件` 非空 → 判定越界写 → 备份回滚/`git checkout --` → `agent_drift` + `FLOW_BATCH_WRITE_SCOPE` + 人工门（B11）。
4. **apply**：审计通过后校验 staging 集合 ⊆ 批内文件 → 备份 → 原子替换 → 记录 `applied_hash`；并行批的 apply 串行化（单写者队列），冲突转人工。

**幂等与不重复（staging-apply 模型）**：
- **写前**：`batch_items.status=running + attempt_id + base_hash`；child 只写 staging，不碰工作区。
- **写后**：插件校验 staging 文件集合 ⊆ 批内文件 → 备份原文件 → 原子替换 → 记录 `applied_hash` 与 receipt。
- **恢复对账**：租约过期 → 批回 `ready`；对每个文件比较工作区 hash 与 `applied_hash`：一致则跳过；staging 有未应用文件则重新校验应用；不一致（外部修改）→ `manual`。
- **批次完成**：批内所有文件 `applied|manual` 才允许 `done`；`repair` 只处理 `failed` 文件，成功文件不重复转换。
- **唯一事实源**：`batch_items`（一个 group 内 `(group_id,file_path)` 唯一）；`batches.files_json` 仅是计划快照。

**隔离语义（可测口径）**：
- **同 wave 且互不依赖的批**：单批失败不阻塞其他批（100% 隔离）。
- **依赖该批的后继 wave**：按策略阻塞（默认暂停 + 通知，可选择"跳过该批继续"或"人工修复"）——这是"依赖安全"而非"隔离失败"。
- 因此 SLO 写"同 wave 隔离率 100%；依赖阻塞按预期发生"，不承诺"全局 100% 不受影响"。

**防死循环**：`max_attempts`（默认 3）、`max_split_depth`（2）、`max_batches_per_tick`、总 token/时间预算、连续无进展计数 → 人工门。

---

## 8. 质量门控（三层：批级 / wave 级 / 聚合级）

**核心原则**：部分迁移状态下**不做全量 build/browser 硬门**，否则第一批永远无法通过。硬门分层执行。

| 层级 | 信号 | 硬门 | 说明 |
|---|---|---|---|
| **批级 batch** | AST/parse、diff 白名单、变更说明、可选 scoped 单测/局部类型检查、LLM 评审 | **parse 失败、越界写、diff 超限 → 直接 rework**；其余为软信号 | 不跑全量 `vite build`/`vue-tsc`/浏览器 |
| **wave 级** | 受影响模块的增量构建（如可判定）、touched routes 的浏览器 smoke | 构建失败 → 该 wave repair；不影响其他 wave | 可选，按项目工具链能力启用 |
| **聚合级 aggregate** | 全量 build、全量 type、浏览器 E2E、覆盖率、五信号加权 | **全量 build 失败 / 关键路由白屏 → 不通过** | 全部批次完成后执行一次；FR-7 硬门在此生效 |

- **批级评分**：可复用 85/70 阈值（AST 20 / diff/类型 15 / 行为 20 / 构建 20 / 浏览器 25 的**批内近似权重**，具体权重在设置中可调）；批级不通过 → repair 子批；`quality_gate_per_batch=false` 时只做 parse/diff 硬检查，评分延后到聚合门。
- **文件级证据**：每个文件必须有 diff + parse 结果 + 变更说明；缺证据按 0 分。
- **聚合级评分**：按文件数加权 + 覆盖率（已应用文件/总文件）+ 硬门（全量 build / 关键路由 browser 通过）；未覆盖率 >0 不允许聚合通过。
- **修复子批**：低分/失败文件组成新批次（batch_size 减半），携带上一轮证据与经验；最多 3 轮。
- **防作弊**：staging 白名单（只允许批内文件）、diff 大小上限、禁止删除测试/跳过校验、`pre_verify` 兜底。
- **成本**：全量 build/browser 只做 **1 次聚合门**（+ 可选 wave 级增量），避免 43 次全量构建。

---

## 9. 成本、并发与预算

| 参数 | 默认 | 说明 |
|---|---|---|
| `max_files_per_batch` | 7 | 按上下文预算与文件大小自适应（1–12）；7 是示例上限参考，实际由预算决定 |
| `context_budget_chars` | 28,000 | 留 4k 给 prompt/工具输出 |
| `max_concurrent_batches` | 1 | 波次串行；可选 2–3（仅同 wave，需 worktree 隔离） |
| `max_batches_per_tick` | 10 | 一次 tick 最多推进批数；同时受 `tick_budget_seconds` 约束 |
| `tick_budget_seconds` | 600 | 单次 tick 时长上限；到点保留 handle/checkpoint 后退出 |
| `wait_slice_seconds` | 60 | 单次 `wait()` 分片，避免阻塞心跳/取消 |
| `batch_timeout_seconds` | 1800 | 单批累计等待上限（跨 tick 累计），超时 cancel + 重试/拆批 |
| `max_attempts` per batch | 3 | 含拆分前重试 |
| `max_split_depth` | 2 | 拆到 single_file 即止 |
| `run_token_budget` / `run_time_budget` | 项目配置 | 超预算暂停 + 人工门（见 §12） |
| 子代理 `max_iterations` | 60（建议） | 比默认 250 低，批次任务更聚焦；通过 `delegation.max_iterations` 全局设置 |
| 结果上限 | lifecycle 32k / delegate 24k | 批次结果按 24k 设计；逐文件 notes 精简 |
| 预估成本 | ~1 次子代理启动/批 + 每文件 token | 287 文件 / 43 批 ≈ 43 次启动；启动开销约 2–4k token/次；全量 build/browser 仅 1 次 |

> 并发建议：初次接入默认 1，观察限流与质量后逐步升到 2–3；**不要超过 3**（生命周期池 8，需留给修复/质量子代理与用户其他任务）。同层并行必须使用独立 worktree/staging，串行合并。

---

## 10. UI / 交互设计（增量）

### 10.1 专家（Agents）
- 专家卡新增徽标：`循环 · 7 文件/批` / `循环 · 串行`。
- 专家详情抽屉新增「批次循环」配置：模式（per_batch/single_file）、每批文件数、并发批次、失败拆分、上下文预算、每批质量门开关。
- 专家卡运行态显示：`批次 18/43 · 文件 126/287`。

### 10.2 工作台（Workbench）
- 当前 Run 卡新增批次进度条：`批次 18/43（42%）· 文件 126/287（44%）`。
- "活跃异常"下钻显示是哪个批次在退避/拆分。

### 10.3 运行监控（Monitor）
- 新增「批次队列」面板：按 wave 分组，列出批次 `#07 · 7 文件 · 运行中 · 评分 88`；支持点击查看批内文件状态（pending/running/done/failed）。
- 时间轴日志增加批次事件：`batch.claim / batch.ingest / batch.gate / batch.split / batch.retry`。
- 证据抽屉：批次级汇总 + 文件级 diff 列表。

### 10.4 编排（Flow）
- `batch` 节点徽标显示 `×43 批`；属性面板新增：批量源（分析报告/glob）、批大小、并发批次、内层循环（serial/single_file）、失败拆分、每批质量门。
- 画布上批次节点可展开为"批次队列"预览（只读，展示前 5 批）。

### 10.5 质量（Quality）
- 评分表按批次分组（可展开到文件）；新增"批次通过率"指标；低分批次可直接"重新审查该批"。

### 10.6 设置（Settings）
- 「批量执行」区块：默认批大小、最大并发批次、每 tick 批数、单批等待超时、拆分策略、上下文预算。

---

## 11. 验收标准（新增）

| # | 用例 | 通过标准 |
|---|---|---|
| B1 | 1000 文件合成项目 → 批次计划 | 批数符合预算；无跨依赖倒置；计划可导出/复现 |
| B2 | 287 文件样例 → 串行批次 | 全部批次 done；文件级覆盖率 100%；聚合门通过 |
| B3 | 批内部分失败 | 只重跑失败文件（repair 子批）；已成功文件不重复处理 |
| B4 | 单批输出截断 | 自动二分拆批后成功；拆分事件可审计 |
| B5 | 429 限流 | 当前波次暂停→退避→恢复；无重复写 |
| B6 | 杀进程（批次运行中） | 重启后租约回收→只重跑未完成文件；无重复 |
| B7 | 低分批次 | 自动 repair 子批→评分提升；3 轮后人工门 |
| B8 | 同层并行（可选） | 仅同 wave 并发；跨 wave 无并发；结果顺序稳定 |
| B9 | 上下文预算 | 每个子代理 context ≤32,000 字符；无截断 |
| B10 | 批次 UI | 批次队列/文件状态/评分/事件实时一致；断线重连补齐 |
| B11 | **越界写** | child 在 staging 写批外文件，或**直接写工作区批外文件（基线审计发现）** → 回滚 + `agent_drift` + 人工门 |
| B12 | **崩溃窗口** | child 写 staging 后被杀 → 重启后 applied_hash 对账，不重复转换/应用 |
| B13 | **结果契约** | lifecycle 文本 JSON 校验 + 一次格式纠正重派；24k 内不截断；失败转 single_file/人工 |
| B14 | **driver 单例** | 两个 cron/会话同时 tick → 只有一个持锁推进；无重复认领/无并发超限 |
| B15 | **多批循环（P2 可选）** | `persistent_child` 连续 ≤3 批，每批 checkpoint；中途取消可从下一批恢复 |
| B16 | **批级硬门分层** | 部分迁移状态下第一批可 pass（AST/diff），全量 build/browser 仅在聚合门失败 |
| B17 | **总预算** | 100 批连续运行不超 Run token/时长预算；超 80% 告警、超 100% 暂停 + 人工门 |

**SLO（批量）**
- 已完成文件重复处理率：0（以 `applied_hash` 对账）
- 崩溃恢复后已完成批次重复执行率：0
- **同 wave 隔离率：100%**（互不依赖批不受影响）；依赖批按策略阻塞（预期行为，不计为隔离失败）
- 事件延迟：P95 ≤1s
- 100 批连续运行：无人工介入完成率 ≥95%（注入 10 次故障）；总时长/总 token 不超 Run 预算
- 批次结果解析成功率 ≥99%（lifecycle 文本 JSON + 校验 + 重派）

---

## 12. 风险与调参

| 风险 | 影响 | 缓解 |
|---|---|---|
| 批次过多 → 启动开销大 | 成本/时长 | 自适应批大小；成功后放大批；上限 12 |
| 批次过大 → 上下文截断 | 质量下降 | 预算装箱；截断即拆；single_file 兜底 |
| 波次并行导致依赖/写冲突 | 编译失败/覆盖 | 仅同 wave 并行；默认串行；依赖闭包校验；**并行批独立 worktree/staging，串行合并** |
| 子代理越界改批外文件 | 质量/污染 | **只写 staging + 插件白名单对账 + 拒绝 apply + agent_drift** |
| 崩溃后重复写/重复转换 | 覆盖人工修改 | **staging + applied_hash 账本 + attempt_id + 租约**；已应用文件跳过 |
| 批级全量构建导致死锁/过慢 | 第一批无法通过 | **批级只做 AST/diff；全量 build/browser 移到聚合门**（+可选 wave 增量） |
| lifecycle 无 output_schema | 结果不可解析 | 提示词约束 + 插件 JSON 校验 + 一次格式纠正重派；仍失败转 single_file/人工 |
| delegate 结果 24k 截断 | 丢文件/重复处理 | 结果按 24k 设计；逐文件 notes 精简；超限拆批 |
| driver 多实例/心跳中断 | 重复认领/超并发 | **Run 级 driver 单例锁 + 独立 heartbeat + wait 分片** |
| handle 跨进程/超 1h 丢失 | 批次卡住 | 租约过期 → ready → applied_hash 对账 → 重派未应用文件 |
| 批次事件过多 → UI 压力 | 卡顿 | 事件聚合 + 分页 + 虚拟列表 |
| 限流窗口内并发过高 | 429 放大 | 默认并发 1；自适应并发（成功 +1，429 -1，上限 3） |
| 总时长/成本失控 | 费用/时间 | 单 Run 总 token/时长预算 + 超支告警 + 人工门 |

---

## 13. 与 PRD 的映射（新增/修改点）

| PRD 位置 | 变更 |
|---|---|
| §1.2 痛点 | 增加"文件太多，单任务上下文装不下、失败重来成本高" |
| §2.1 目标 | G2 增加"批次循环"；新增 G9（批量吞吐/失败隔离） |
| §7 功能需求 | **新增 FR-10 批量循环与批次调度**；FR-1 专家增加 loop_policy；FR-3 batch 节点细化；FR-6 增加批级恢复；FR-7 增加批级/聚合门 |
| §8 工作流引擎 | 新增 §8.4 批次规划与调度（算法/状态机/幂等） |
| §9 多智能体协议 | 新增 §9.4 批次执行通道（lifecycle vs delegate_task vs kanban）与 Batch Packet |
| §12 记忆 | 经验按批次沉淀；repair 子批复用同批经验 |
| §13 UI | 新增批次队列/进度/配置（10.1–10.6） |
| §14 实现 | 新增 `core/batch/`、`flow_batch_*` 工具、batches/batch_items 表、API |
| §15 计划 | M2 增加批次调度；M3 增加批级恢复/拆分 |
| §16 验收 | 增加 B1–B17 与批量 SLO |
| 附录 G | 批次 DSL/配置/伪代码/证据索引 |

---

## 附录 A：Hermes 证据索引

| 声明 | 证据 |
|---|---|
| `delegate_task` 批量 tasks、background、结构化输出 | `E:\hermes\hermes-agent\tools\delegate_tool.py:483-513` |
| 并发默认 10、超限报错、线程池、结果排序 | `tools/delegate_tool_config.py:17`；`tools/delegate_tool.py:543`；`tools/delegate_tool_tasks.py:83`；`delegation.md:211-215` |
| 批量是一个 async unit、group/independent completions | `delegation.md:184-209` |
| 完成事件持久化但不恢复 child 执行 | `delegation.md:219-233` |
| 子代理迭代上限 250（全局）、默认无 wall-clock 超时、停滞阈值 450s/1200s | `delegation.md:342-380`；`delegate_tool.py:105,111-112`；`delegate_tool_config.py:24-27` |
| leaf 禁止再委派；orchestrator 受 max_spawn_depth（默认 1） | `delegation.md:329-342`；`delegate_tool_config.py:21,151-167`；`delegate_tool.py:226-229` |
| **delegate_task summary 上限 24,000** | `tools/delegate_tool_results.py:160,163,166,275-277` |
| `ctx.dispatch_tool` 在 gateway 下 parent_agent 可能为 None | `hermes_cli/plugins.py:674-683` |
| `subagent_lifecycle` launch/wait/cancel、字段与上限、timeout 被拒、并发 8、进程内 | `agent/subagent_lifecycle.py:25-28,120,159-160,221-228,277-280,371-375`；`developer-guide/subagent-lifecycle-api.md:15-64` |
| kanban dispatcher：gateway 内嵌、60s tick、依赖/回收 | `website/docs/user-guide/features/kanban.md:122-140,314-325` |
| 前序拓扑排序可复用 | `E:\DHLocal\HERMES\vue3migrate-core\vue3migrate_core\migrator.py:134` |
| 前序调度器串行/切片 | `...\engine\scheduler.py:132-215` |

## 附录 B：批次 DSL 示例

```json
{
  "id": "transform",
  "type": "batch",
  "name": "代码转化",
  "agent": "代码转化专家",
  "skills": ["vue3-transform", "vuex-to-pinia"],
  "batch": {
    "source": "report:deps.files",
    "order": "topo",
    "size": 7,
    "adaptive": true,
    "context_budget_chars": 28000,
    "inner_loop": "serial",
    "concurrency": 1,
    "max_split_depth": 2,
    "split_on_failure": true,
    "quality_gate_per_batch": true,
    "write_mode": "staging_apply"
  },
  "depends_on": ["deps"]
}
```

## 附录 C：设计决策摘要

1. **批次是最小治理单元**：有独立状态、租约、评分、证据、重试/拆分。
2. **文件是最小幂等单元**：`(group_id,file_path)` 唯一；staging → 原子应用 → `applied_hash` 账本。
3. **默认串行、同层可并行**：依赖安全优先，吞吐次之；并行批必须独立 worktree/staging。
4. **生命周期子代理为首选通道**：插件可控 model/toolsets、逐批归因；`delegate_task` 批量作为加速/降级（结构化 schema 原生支持，但结果上限 24k）。
5. **批内循环放在子代理**：一次 launch 处理一批，减少启动开销，同时保持上下文隔离；一个子代理一次只处理 1 批（P0）。
6. **质量门分层**：批级 AST/diff；wave 级可选增量；**全量 build/browser 只在聚合门**（避免部分迁移死锁）。
7. **driver 单例 + 心跳 + wait 分片**：跨 tick/跨进程用租约与 applied_hash 对账续跑，不依赖 handle 存活。
8. **聚合门不能省**：批级通过 ≠ 项目通过；最终必须全量构建 + 关键路由验证 + 覆盖率 100%。
