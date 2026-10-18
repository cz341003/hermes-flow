# 批量拆批 + 子代理循环：第二轮新增需求增量复审（QA Batch Review）

> **评审对象（2026-10-18 14:14–14:30 快照）**：
> - `research/batch-loop-analysis.md`（33,025 B / 532 行 / 14:12:12）
> - `docs/PRD.md` v2.2（111,657 B / 1,418 行 / 14:14:21，新增 FR-10 / §8.4 / §9.4 / 附录 G）
> - `docs/FEASIBILITY.md`（22,480 B / 256 行 / 14:13:59，新增需求 9 / 批次调度缺口）
> - `ui-design/index.html`（318,112 B / 14:17:12，批次 UI 组件已开始落地）；`design-spec.md`（13:25:32）、`PROMPTS.md`（13:25:32）、`screenshots/`（13:25:39–13:26:11）**尚未包含批次内容**（UI 方仍在重建）
> - 宿主证据：Hermes Agent v0.22.2（`E:\hermes\hermes-agent`，commit `d923a5e`）；本报告新增抽查 `tools/delegate_tool*.py`、`tools/delegate_tool_config.py`、`tools/delegate_tool_tasks.py`、`tools/delegate_tool_results.py`、`agent/subagent_lifecycle.py`、`hermes_cli/plugins.py`、`website/docs/.../delegation.md`、`.../cron.md`、`.../kanban.md`
> **评审方式**：只读核对源码/官方文档 + PRD/FEAS/analysis 交叉比对 + 逻辑推演；不修改任何交付物；未验证项标"待确认"。

---

## 0. 总评

**结论：有条件通过（Conditional Pass）——方案方向正确、Hermes 事实核验基本可靠；但 7 项 P1 必须修正后才能进入实现，UI 批次可视化需在冻结后复核。**

- **P0 = 0**（未发现"API 完全不可用/方案根本跑不通"的硬阻塞；所有 P1 都有可实现路径）。
- **P1 = 7**（结果契约、写入/幂等、调度/租约、质量门粒度、需求语义等——其中 3 项直接导致 B2/B3/B6/B9 无法验收，等同于实现前阻塞）。
- **P2 = 17**（口径不一致、证据行号、数据模型细节、UI/四件套版本漂移等）。

**一句话理由**：analysis 对 Hermes 两种批量通道的事实抽查 20+ 处，绝大多数准确（默认 10 并发/超限报错、批量=一个 async unit、完成事件持久化但不恢复 child、250 迭代/默认无 wall-clock 超时/450s·1200s 停滞阈值、lifecycle 8 线程池/需活跃父会话/timeout 被拒/32k 上限）；批次规划（拓扑分层+预算装箱）、状态机、失败矩阵、B1–B10 与 PRD 新增章节总体自洽。主要问题在**"批次"的接口契约与质量门语义**：lifecycle 通道不支持 `output_schema`、Batch Packet 不含文件内容却按内容估算预算、批级 build/browser 硬门在部分迁移状态下不可行、写入治理与幂等窗口未闭环、缺少 driver 单例/心跳与 tick 预算的协调——这些会让"每批一个子任务、子代理循环、失败隔离、断点续跑"在验收时站不住。

---

## 1. 阻塞级问题（P0，必须改）

**无。** 所有 P1 均可用"解析/校验文本结果 + 本地 checkpoint + 轮询/隔离 + 门控分层"实现，不涉及"Hermes 不支持"的硬阻塞。

> 但需明确：**P1-2、P1-3、P1-7 若不修，B2（全批完成+聚合门）、B3（部分失败只重跑失败文件）、B6（杀进程续跑）、B9（context ≤32k）四个验收项按现状无法证明通过**——从"能否验收"角度等同阻塞。

---

## 2. 重要问题（P1）

### P1-1　`batch` 节点配置存在三套互不一致的 schema（P0 特性的实现歧义）
- **FR-3 节点表**（`PRD.md:337`）：`batch` 节点字段 = `glob、batch_size、concurrency`；
- **§8.1 DSL 示例**（`PRD.md:624`）：`"batch":{"from":"reports/deps.json","size":1,"strategy":"topo","parallel":false}`；
- **§8.4 / 附录 G / Batch DSL**（`PRD.md:676-681`、`PRD.md:1371-1385`）：`source/order/size/adaptive/context_budget_chars/inner_loop/concurrency/max_split_depth/split_on_failure/quality_gate_per_batch/write_scope`；
- 三套字段名、默认值（size 1 vs 7、parallel vs concurrency）都不同，且 `source` 与 `from` 语义重叠。
- **影响**：P0 特性的 DSL schema 无单一事实源，M2 实现与模板迁移会返工；`flow_workflow_validate` 无法确定校验规则。
- **修法**：以 §8.4/附录 G 为唯一 schema（`source/order/size/adaptive/...`），把 FR-3 表与 §8.1 示例改引用该 schema；如需兼容旧字段，明确 deprecated alias 与迁移规则。

### P1-2　"子代理返回结构化逐文件结果"在首选通道（lifecycle）上不可强制
- **PRD**：`PRD.md:771` "逐文件结果必须结构化（`output_schema`）"；`PRD.md:572` 与 analysis §6.2（`batch-loop-analysis.md:288-330`）把 `output_schema` 放进 Batch Packet。
- **源码事实**：`SubagentLaunchRequest` **没有 `output_schema` 字段**（`agent/subagent_lifecycle.py:48-62`）；`SubagentResult` 只有 `summary`/`structured_payload`（`:114-127`），而 `structured_payload` 在全仓**仅声明、从未赋值**（全仓 grep 仅 `:120` 一处）；lifecycle API 文档也未提供 schema 校验/纠正轮。带 `output_schema` 的是 `delegate_task` 的 task 字段（`delegate_tool.py:730-732`、`delegation.md:55-78`）。
- **影响**：插件无法保证 child 返回可解析的逐文件 JSON；1 批 7 文件中一个格式错误就可能导致整批 ingest 失败/重复处理。B3/B9 与 §9.4 的"结构化"承诺无支撑。
- **修法**（二选一或组合）：① lifecycle 通道改为"文本 JSON + 插件侧 JSON Schema 校验 + 一次格式纠正重派"，并把该契约写进 `Batch Packet`/工具错误码；② 明确 `delegate_task` 波次（其支持 per-task `output_schema`）为结构化批次的通道，但需定义"主 Agent 收到结果后回灌插件"的工具（见 P2-15）。**不要**在文档中声称 lifecycle 支持 `output_schema`。

### P1-3　文件写入治理与幂等窗口未闭环（越界写 / 崩溃重复处理 / 去重键）
- **越界写**：`PRD.md:572` 与 `:1260` 声称"只允许修改批内文件（写入白名单 + diff 校验）"，analysis `:333,375` 同样声明；但**没有定义执行机制**：child 在 `working_directory` 内拥有 file/terminal 工具，lifecycle 不支持按路径限制写入；`pre_verify` 也只在"编辑过代码"时触发、不能阻止越界路径。需要"启动前记录文件集/哈希 → child 结束后 `git diff --name-only`（或全量哈希）比对白名单 → 越界文件回滚 + `agent_drift` + 人工门"的明确流程与验收（B1–B10 中没有越界写用例）。
- **崩溃窗口**：`attempt_id` 只约束"插件写回"（`PRD.md:1134`），但迁移是 **child 直接写工作区文件**；若 child 写完文件、未回灌就被杀，`batch_items` 仍为 pending，重跑会对已迁移文件再次执行转换（非幂等转换会二次改写）。`PRD.md:1197` 的"重复处理率 0"在当前机制下无依据。
- **去重键不一致**：PRD `:1134` 用 `(file_path, content_hash)`；analysis `:229` 用 `(group_id, file_path, content_hash)`；`batch_items` 表（`PRD.md:1119-1122`）**没有唯一约束**，索引（`:1135`）也没有该组合。跨 Run 同文件同 hash 会冲突；无唯一约束则"去重"只是查询约定。
- **修法**：① 增加"预写快照 + 结束对账 + 越界回滚"流程与 B11 验收；② 明确 content_hash 的语义（迁移后 hash / 原始 hash / 双哈希），并以 `(group_id, batch_id, file_path)` 建唯一约束，content_hash 用于"已完成内容一致性"而非主键；③ 在 `batch_items` 增加 `attempt_id`/`version`，把"当前 attempt 才可写"落到 schema（现表只有 `attempts` 计数）。

### P1-4　调度/租约模型与 tick 预算、心跳、driver 单例不协调
- **默认值冲突**：`PRD.md:1269`/附录 G `:1399-1402`：`max_batches_per_tick=10`、单批 `wait=1800s`；而 §17 的 turn/tick 预算为"10 分钟/20 节点"、cron 每 5 分钟（`PRD.md:807`）。同步 `wait()`（`subagent_lifecycle.py:332`）最多可阻塞 30 分钟/批，完全可能超出 tick 预算；§8.4 `:712` 用"（或分多次 tick 轮询）"带过，但没定义跨 tick 的 handle 持久化与超时回收。
- **心跳/租约**：批次租约 TTL 与 30s 心跳（`PRD.md:566`）需要一个持续运行的 driver；若 driver 在 `wait()` 上阻塞，心跳线程/下一次 tick 无法保证，容易被其他 driver 判为过期并重复认领。§8.4 只说"调度器单线程（tick 驱动）"，**没有 driver 单例锁**（多 cron 会话/多 driver 并发时会突破 `max_concurrent_batches` 与 wave 串行）。
- **相关宿主事实**：lifecycle 句柄/结果**只在进程内保留 1 小时**（`subagent_lifecycle.py:29` `_TERMINAL_RETENTION_SECONDS=3600`），跨进程 `reconnect` 返回 `RECONNECT_UNAVAILABLE`（`:371-375`）；"分多次 tick 轮询"只在同进程、1h 内成立（cron 在 gateway 进程内跑 isolated agent session——**待确认** job 是否恒为同进程）。若下次 tick 在新进程（或超 1h），handle 丢失。
- **修法**：① 把单批 `wait` 改为"小步等待/轮询"（如 `wait(timeout≤60s)` + `status`），tick 预算内干净退出；② 增加 **Run 级 scheduler lease**（单写者）与独立 heartbeat（后台任务/异步循环），并把 `max_concurrent_batches`、wave 串行作为租约前置条件；③ 明确 driver 进程模型与 handle 失效兜底（丢失→租约过期→批回 ready→按 hash 对账）；④ 默认 `wait_seconds` 与 tick 预算做一致性校验（见 §17）。

### P1-5　`delegate_task` 子代理结果上限被写成 32,000（实际 summary 硬上限 24,000）
- **PRD**：`PRD.md:771` "子代理结果 ≤32,000 字符"（作为两种通道的通用约束）；附录 G `:1409-1411`；analysis `:66` "child 结果 ≤32k 字符（文档口径）"、`:96`。
- **源码事实**：`delegate_task` 的 child 摘要受 **`DEFAULT_MAX_SUMMARY_CHARS = 24000`** 硬上限 + 父上下文 headroom 动态预算约束（`tools/delegate_tool_results.py:160,163,166,275-277`），超出会截断为 head/tail 并落盘 spill；而 **32,000 是 `ctx.subagent_lifecycle` 的 result/context 上限**（`subagent_lifecycle.py:26-28`；`subagent-lifecycle-api.md:54`）。delegation.md 并未给 delegate_task 的 32k 口径。
- **影响**：若把 delegate_task 作为"加速/降级"通道，7 文件批次的逐文件结果 JSON 可能在 24k 处被截断——插件解析失败/丢文件，触发重复处理；同时"结果超限"被列为异常（`PRD.md:786`），但上限数值写错会误导实现与验收。
- **修法**：区分两条通道的上限：lifecycle result/context = 32,000 字符；delegate_task summary = 24,000 字符（可配 `max_summary_chars`，且受 headroom 影响，可能更小）。批次结果契约按 24k 设计（或强制 delegate 通道每批更小）。

### P1-6　需求缺口：用户"专家可配置循环完成某一批/多批"的"多批"语义未落地/未验收
- **用户诉求**：每批一个子任务；专家可配置"循环完成某一批/多批"。
- **PRD 现状**：`loop_policy` 有 `mode = per_batch | single_file | persistent_child`（`PRD.md:537-553`）、`max_batches_per_launch`（`:544`），但正文 L3 写"一次 launch 处理整批"、`persistent_child` 标注"不推荐，仅超小项目"（`:553`）；附录 G 又把 `persistent_child` 列为"不推荐"（`:1394`）。**"一个子代理循环多批"既没有执行流程/暂停恢复定义，也没有 B1–B10 验收**。
- **影响**：若用户的"多批循环"是硬需求，本方案实际只实现了"插件循环批次 + 子代理循环批内文件"（L1+L3）；`max_batches_per_launch>1` 的语义空白会让实现方自由发挥。
- **修法**：二选一：① 明确"多批循环"= `persistent_child`/`max_batches_per_launch>1`，给出 child 内 batch 循环、上下文滚动、checkpoint、取消语义与独立验收（B 系列新增）；② 与用户确认口径，把配置收敛为"每批一个子任务 + 子代理批内循环"，并从枚举删除 `persistent_child`、删除 `max_batches_per_launch`（减少误导）。

### P1-7　批次级质量门与失败隔离语义不可达（质量门粒度 + SLO 100%）
- **质量门粒度**：`PRD.md:587` "每批五信号评分（构建/类型/浏览器可用增量检查）"；但 FR-7 的硬门是"构建失败/浏览器白屏直接不通过"（`PRD.md:473,700`）。在**部分迁移**状态下，全项目 `vite build`/`vue-tsc`/启动浏览器都会因未迁移文件而失败——若严格按硬门执行，**第一批就不可能通过**（死锁）；analysis `:371` 只说"增量/局部检查（只构建受影响模块或整包快速构建）"，没有可执行方案（Vite 无模块级 build；vue-tsc 无"只查一批文件"的稳定模式）。
- **失败隔离 SLO**：`PRD.md:1198` "批次失败隔离率 100%（注入单批失败，检查其他批是否继续/不受影响）"；analysis `:443` 同。但在"同 wave 独立批可继续、跨 wave 依赖批必须阻塞"的语义下，100% 不成立；默认 `max_concurrent_batches=1` 时同 wave 也不会"继续"。
- **修法**：① 把批级信号限定为"文件级 AST/parse + 受影响的局部 type-check/单文件编译"，**全量 build/browser 只在聚合门**执行；FR-7 硬门在 batch 节点明确豁免；② 把 SLO 改为"同 wave 且互不依赖的批不受影响；依赖批按策略阻塞并进入 manual/继续选项"并给出可测口径；③ 明确 43 次 build/browser 的成本与替代（仅聚合门做一次全量）。

---

## 3. 建议改进（P2）

1. **批次数量与默认值不一致**：analysis §0 `:26` 写"42 批 × 7 文件"，§4.3 `:156-165` 与 PRD G9 `:75`/附录 G `:1399` 为"43 批/7 文件"；analysis §4.1 `:124` 写 `max_batch_size=12（默认 5）`，§9 `:383` 与 PRD `:543,677` 默认 7；§4.2 `:152` 又给出"平均 6KB → 每批 4 文件 → 72 批"，与"7 文件→43 批"矛盾（7×6KB×1.2+2000 已超 28k 预算）。建议：默认值统一为 7，并把"7"表述为"上限参考，实际由预算装箱决定"，同时修正两个示例。
2. **PRD 版本号残留**：头部 `PRD.md:5` 已是 v2.2，但 `:57,95,133,1140,1306` 仍写 v2.1（§14.7 表头 "v2.1 处理"、附录 D "v2.1（本文件）"）。统一为 v2.2 或注明"v2.2 为 v2.1 增量"。
3. **里程碑计数**：`PRD.md:1150` "5 个里程碑"与表内 M0–M5（含可选 M5）不一致；建议写"5 个核心里程碑 + 1 个可选（M5）"。
4. **工具数量**：`PRD.md:1044` "首批 26 个"与表内实际（11 行、合计 39 个工具名：agent5+skill3+workflow5+run5+turn5+batch7+gate2+recovery2+exp2+pref2+board1）不符；`:247` 仍写"20+ 个 flow_* 工具"。建议统一为"39 个（按组 11 类）"或明确只统计 `flow_*` 单项（`flow_batch_plan/next/...` 计 7 个）。
5. **证据行号错误**：analysis `:59` 与附录 G `:1409` 引 `tools/delegate_tool.py:17` 作为 `_DEFAULT_MAX_CONCURRENT_CHILDREN=10` 的出处——实际常量在 **`tools/delegate_tool_config.py:17`**（`delegate_tool.py:17` 是 import）；analysis `:64,491` 与附录 G `:1412` 引 `delegate_tool.py:21` 作为 `max_spawn_depth` 默认值——实际在 **`delegate_tool_config.py:21`（`MAX_DEPTH=1`）**。`delegate_tool.py:226-229,483-513,105,111-112` 等其余行号正确。
6. **宿主文档自身冲突（需标注）**：`delegation.md:211` 与源码常量均写默认 **10**；但 `website/docs/user-guide/configuration.md:2950,2983` 写"default 3"。analysis `:59` 采信 10 是对的，建议加注"以源码/官方 delegation 文档为准，configuration.md 示例过期"，避免评审争议。
7. **批次示例与依赖方向矛盾**：analysis `:156-165` 把 router/store/entry 放在 wave4"最后关键批"；但若组件 import store，依赖边会使 store 处于**低 wave**（应先迁移）。建议修正示例（store 拆分/前置）或说明"高风险=最后"仅适用于 router/entry（其依赖 views），store 单独前移。
8. **高优先批"先跑"表述**：analysis `:146` 写 `batch.priority=high（先跑/单独批次）`，与 wave 依赖顺序冲突；PRD `:561` 只写"单独成批+人工复核"（正确）。建议删除"先跑"，保留"提前人工复核/优先展示"。
9. **数据模型细节**：`PRD.md:1109-1135` 的 batch 表缺少：`batch_items` 唯一约束/`attempt_id`（P1-3）；`batch_receipts` 无 `(batch_id,attempt,event)` 唯一键；`gates` 表无 `batch_id`（人工门只能挂 node，无法精确到批）；`batch_groups` 无聚合门分数/verdict 字段；`batches.files_json` 与 `batch_items` 维护两份文件清单（需明确唯一事实源）。另 `PRD.md:1060` 要求"写操作 expected_version"，batch 表无 version 列。
10. **批级质量规则未定义**：批级 pass/warn/rework 阈值是否复用 FR-7 的 85/70、`quality_gate_per_batch` 关闭时的行为、聚合门的通过阈值与覆盖率门槛（PRD `:587` 只说"聚合门"）均未写。
11. **批级异常/错误码缺失**：FR-10 失败表（`:574-583`）的 `split/repair/manual` 未映射到 §10.1 异常分类或附录 C 的 `FLOW_*` 错误码（附录 C `:1116` 仍只有 12 个错误码）；建议新增 `FLOW_BATCH_*`（overflow/split/lease/duplicate/write_scope 等）。
12. **跨 tick 轮询的进程/保留期假设未写**：`PRD.md:712` "分多次 tick 轮询"依赖"同进程 + handle 1h 内"（`subagent_lifecycle.py:29`），跨进程不可用（`:371-375`）；cron job 是否恒在 gateway 同进程执行**待确认**（`cron.md:338` 只写"gateway daemon ticks、isolated agent sessions"）。建议在 §8.4 写明 driver 进程模型与超 1h/换进程的回收策略。
13. **同层并行的物理隔离未考虑**：`PRD.md:534` 允许同 wave 并发 2–3；但多 child 在同一工作区并发写不同文件时，**git diff 归因、vite build/vue-tsc 并发、dev server 端口冲突**都会互相干扰。analysis 未提 worktree；lifecycle 有 `working_directory`（`subagent_lifecycle.py:56`）、delegate_task 有 `delegation.worktree_isolation`（`delegate_tool_config.py:115-117`）。建议：并行批默认禁用质量门或将每批放到独立 worktree/临时目录，串行合并。
14. **FEASIBILITY §0 自研清单漏批次调度**：`FEASIBILITY.md:16-18` 的"需要插件自研"仍列 5 项（①–⑤），但同文 `:174-180` 已写"六大缺口"且第 3 项是批次调度；应补 ⑥ 或改成"见 §4 六项"。
15. **`delegate_task` 通道的结果回灌路径未定义**：`PRD.md:765` 说"一次调用一批批次"，但插件无法直接调用 `delegate_task`（gateway 下 `dispatch_tool` 的 parent_agent 为 None，`plugins.py:674-683`）；主 Agent 收到 child 结果后，需要什么工具把逐文件结果写回 `batch_items`？`flow_batch_*`（`:1053`）没有 ingest/ingest-results。建议增加 `flow_batch_ingest` 或在 `flow_batch_complete` 明确 results 入参。
16. **成本/时长预算缺失**：analysis `:386-391` 给 `wait_seconds=1800`、`max_batches_per_tick=10`，最坏单 tick 5 小时；43 批串行按 1800s 上限最坏 21.5h，但 PRD 没有总时长/总 token 预算与告警阈值；B"100 批 10 故障压测"（`:601,1224`）也没有时间上限。建议加"单 Run 总 token/时长预算 + 超支人工门"并进 SLO。
17. **UI 四件套版本不一致（放行前置）**：`index.html` 14:17 已加入批次 UI（batch-progress `:1443-1483`、workbench `批次 18/43` `:1975-1983`、monitor 批次队列 `:2897-2975`、flow `×43 批` `:2659` 与批量属性 `:2749-2775`、专家循环徽标 `:2195` 与抽屉 `:3908-3914`、质量"批次通过率/按批次" `:3451,3559`、设置"批量执行" `:3736-3744`）；但 `design-spec.md`、`PROMPTS.md`、`screenshots/` 仍是 13:25 的**无批次版本**。放行前必须冻结 index 并重渲 9 图，同时把 §10.1–10.6 UI 增量写进 design-spec/PROMPTS；否则"UI 可见"无法验收（B10）。

---

## 4. Hermes 事实核验表（新增抽查，20 条）

| # | 声明（analysis / PRD） | 证据（file:line） | 判定 |
|---|---|---|---|
| 1 | `delegate_task(tasks=[...])` 批量；`background` 对单任务/批量都生效；每项支持 `output_schema/images/group/role` | `tools/delegate_tool.py:483-493,730-743`；`delegation.md:184-209` | ✅ |
| 2 | 批量并发默认 **10**（`delegation.max_concurrent_children`/env，floor 1、无硬上限） | `tools/delegate_tool_config.py:17`；`delegate_tool.py:543`；`delegation.md:211` | ✅（宿主 `configuration.md:2950,2983` 写 default 3，属上游文档冲突） |
| 3 | 批次大于上限**返回工具错误**而非截断/排队 | `tools/delegate_tool_tasks.py:83`；`delegation.md:211` | ✅ |
| 4 | 批量 = 一个 async unit；默认全部完成后一条汇总；结果按 task index 排序 | `delegate_tool.py:511-513`；`delegation.md:184-215` | ✅ |
| 5 | `independent_completions` 开启后按 group/独立返回 | `delegate_tool_config.py:110-113`；`delegation.md:188-209` | ✅ |
| 6 | 完成事件先写 `state.db` 再投递；重启恢复投递但**不恢复 child 执行**、丢失 owner 记 `unknown` | `delegation.md:219-233` | ✅ |
| 7 | child 迭代上限默认 **250**（全局 `delegation.max_iterations`，非 per-call） | `delegate_tool.py:105`；`delegation.md:342-354` | ✅ |
| 8 | **默认无 wall-clock 超时**；heartbeat 停滞阈值 450s idle / 1200s in-tool；`child_timeout_seconds` 仅"无进展"上限 | `delegate_tool_config.py:24-27`；`delegate_tool.py:111-112`；`delegation.md:356-380` | ✅ |
| 9 | `leaf` 不能再委派；`role=orchestrator` 受 `max_spawn_depth`（默认 1）限制 | `delegate_tool_config.py:21,151-167`；`delegate_tool.py:226-229,516-520`；`delegation.md:329-342` | ✅（默认 1 = 扁平，orchestrator 无嵌套空间） |
| 10 | `ctx.subagent_lifecycle.launch/wait/status/cancel/steer/result/reconnect` | `hermes_cli/plugins.py:386-391`；`subagent-lifecycle-api.md:15-64`；`subagent_lifecycle.py:269-375` | ✅ |
| 11 | 请求字段含 `timeout_seconds` 但**被显式拒绝** | `agent/subagent_lifecycle.py:48-62,228` | ✅ |
| 12 | 上限：goal 16,000 / context 32,000 / metadata 8KB / result 32,000 字符 | `subagent_lifecycle.py:25-28,221-228,462`；`subagent-lifecycle-api.md:54` | ✅ |
| 13 | 进程内线程池 `max_workers=8` | `subagent_lifecycle.py:159-160` | ✅ |
| 14 | 需要活跃父会话；children 仅进程内；重启 `RECONNECT_UNAVAILABLE` | `subagent_lifecycle.py:277-280,269-272,371-375` | ✅ |
| 15 | lifecycle 结果 `structured_payload` 可承载结构化输出 | `subagent_lifecycle.py:120`（仅声明，全仓无赋值） | ❌ 见 P1-2 |
| 16 | `dispatch_tool` 在 gateway 下 parent_agent 可能为 None | `hermes_cli/plugins.py:674-683`（注释："In gateway mode _cli_ref is None"） | ✅ |
| 17 | kanban dispatcher：gateway 内嵌、默认 60s tick、崩溃回收/依赖 promote | `website/docs/user-guide/features/kanban.md:138` | ✅ |
| 18 | **`delegate_task` 子代理结果 ≤32k（文档口径）** | `tools/delegate_tool_results.py:160,163,166,275-277` → **24,000 硬上限** + headroom；32k 仅 lifecycle | ❌ 见 P1-5 |
| 19 | 前序 `topo_order_files` 可复用 | `E:\DHLocal\HERMES\vue3migrate-core\vue3migrate_core\migrator.py:134` | ✅ |
| 20 | batch 证据行号 `delegate_tool.py:17` / `:21` | 实际在 `delegate_tool_config.py:17`（默认并发）/`:21`（MAX_DEPTH） | ❌ 见 P2-5 |

---

## 5. 需求覆盖矩阵（用户第二轮补充需求）

| # | 用户要求 | PRD 落点 | UI 落点（14:17 index） | 验收 | 判定 |
|---|---|---|---|---|---|
| 1 | 大项目把待转化文件**拆成多个批次** | FR-10 `:527-561`、§8.4 `:672-714`、附录 G | 工作台批次进度 `:1975-1983`；监控批次队列 `:2897-2975`；flow `×43 批` `:2659` | B1/B2；PRD `:1182`、`:592-593` | ⚠️ 算法成立，但批数/默认值不一致（P2-1）、schema 三套（P1-1） |
| 2 | **每批作为一个子任务交给子代理** | FR-10 执行通道 `:567-572`、§9.4 `:760-775` | 监控批行/批内文件/证据 `:2907-2975,3207` | B2/B3 | ✅ 通道成立（lifecycle 首选）；⚠️ 结构化结果受限（P1-2） |
| 3 | 专家可配置**循环完成某一批/多批** | `loop_policy` `:537-555`（mode/inner_loop/max_files_per_batch/…） | 专家卡循环徽标 `:2195`、抽屉循环配置 `:3908-3914` | **无对应 B 项** | ⚠️ "多批"语义未定义/未验收（P1-6） |
| 4 | **失败隔离**（单批失败不影响其他） | FR-10 失败表 `:574-583`、状态机 `:565,703-709` | 监控异常/修复 `:3020-3100` | B3/B7/B8；SLO `:1198` | ⚠️ SLO 100% 不可达（P1-7） |
| 5 | **断点续跑**（文件级） | FR-10 `:580,585`、§10.3 `:796-801` | 监控断点续跑/检查点 `:2934` 等 | B6 | ⚠️ 写-回灌窗口与去重键（P1-3） |
| 6 | **UI 可见**（批次队列/循环配置/进度） | §13.3 `:937-944`、§13.1 `:917-924` | index 已有局部实现（见 P2-17） | B10 | ⚠️ design-spec/PROMPTS/screenshots 未同步（Gate） |
| 7 | **并发/限流**（批间串行、可选同层并行） | §8.4 `:712`、§17 `:1269` | 设置"批量执行" `:3736-3744` | B5/B8 | ⚠️ driver 单例/心跳/wait 冲突（P1-4） |
| 8 | **质量门粒度**（批级） | FR-10 `:587`、§11 | 质量页"批次通过率/按批次" `:3451,3559` | B2/B7 | ⚠️ 批级 build/browser 硬门不可行（P1-7） |
| 9 | **成本可控** | analysis §9 `:379-393` | 设置配额页（旧） | 无 | ⚠️ 无总预算/时长 SLO（P2-16） |

---

## 6. 逻辑漏洞清单（按用户点名维度）

| 维度 | 是否存在漏洞 | 说明 / 证据 | 级别 |
|---|---|---|---|
| 依赖安全 | 基本成立，但有边界漏洞 | 拓扑分层+wave 串行保证"文件级 import 依赖"；但：① 迁移可能改变 import（新增 antdv/组合式依赖），计划不会重算；② analysis `:156-165` 把 store 放最后 wave 与依赖方向矛盾；③ priority=high "先跑"（`:146`）可能破坏 wave 顺序 | P2-7/P2-8 |
| 批内越界写 | **有** | 只有"写入白名单 + diff 校验"的文字声明，无执行机制、无 B 验收；child 工具无法按路径限制写 | **P1-3** |
| 重复处理 | **有** | child 直写工作区 → 崩溃在"写文件后、结果回灌前"会重复转换；`attempt_id` 只约束插件写回；去重键三处不一致且无唯一约束 | **P1-3** |
| 并发/限流 | **有** | 无 driver 单例锁，多 tick/多 driver 可突破 `max_concurrent_batches`；同步 wait（1800s）阻塞心跳与 tick 预算；429 自适应并发有设计但无实现约束 | **P1-4** |
| 质量门粒度 | **有** | 批级 build/vue-tsc/浏览器信号在部分迁移状态下不可行；硬门会死锁；43 次全量构建/浏览器成本未评估 | **P1-7** |
| 成本 | 部分覆盖 | analysis 有"43 次启动/2–4k token/次"估算，但 PRD 无总 token/时长预算/告警；最坏单 tick 5h、单 Run 21.5h | P2-16 |
| 结果契约 | **有** | lifecycle 无 output_schema；`structured_payload` 未实现；delegate 实际 24k 非 32k | **P1-2 / P1-5** |
| 配置一致性 | **有** | batch 节点三套 schema；loop_policy 字段语义（max_batches_per_launch）空白 | **P1-1 / P1-6** |

---

## 7. UI / 设计交付状态（批次增量）

- `index.html`（14:17:12）已包含：批次进度条（`:1443-1483`）、工作台 `批次 18/43 · 文件 126/287`（`:1948,1975-1983`）、监控"批次队列/WAVE 分组/批内文件"（`:2897-2975`）、flow 节点 `×43 批` 与批量属性面板（`:2659,2749-2775`）、专家卡"循环 · 7 文件/批"与抽屉配置（`:2195,3908-3914`）、质量页"批次通过率/按批次"（`:3451,3559`）、设置"批量执行"（`:3736-3744`）、事件 `batch.claim/ingest/gate/split/retry`（`:3075-3095`）。**方向与 PRD §13.3 一致**。
- `design-spec.md`（13:25:32）、`PROMPTS.md`（13:25:32）、`screenshots/`（13:25:39–13:26:11）仍是**无批次版本**；旧截图中 workbench 仍是"100 批次/单批 3 文件"口径（PROMPTS `:59`），与新 UI 的"43 批/7 文件"冲突。
- **放行前置**：冻结 `index.html` → 重跑 `screenshot.ps1` 重渲 9 图 → 把 §10.1–10.6 UI 增量写进 `design-spec.md`/`PROMPTS.md`；复核"批次队列/专家循环配置/batch 节点/批量设置"四要素与数值（43/7/18/287/126）一致。

---

## 8. 放行条件

1. **修 P1-1（schema 统一）、P1-2（结果契约）、P1-3（写入/幂等）、P1-4（调度/租约）、P1-5（24k/32k）、P1-6（多批语义）、P1-7（质量门/隔离 SLO）**；其中 P1-2/P1-3/P1-7 需同步补 B11–B13 验收。
2. **UI 批次四件套同步 + 重渲截图**（P2-17）。
3. **P2-1～17 可并行清理**；建议优先 P2-8（数据模型唯一键/attempt_id/batch_id 门）、P2-13（并行 worktree 隔离）、P2-16（总预算）。

**替代判定**：若 Lead/用户接受"先实现串行 per_batch、暂不做多批循环与同层并行"，则 P1-6 可降级为 P2（删除 persistent_child/max_batches_per_launch 并写清未来项），P1-1/P1-2/P1-3/P1-4/P1-5/P1-7 仍需修。

---

## 9. 核验方法与局限

- 只读：`read`/`grep` 定向核对源码与官方文档；PowerShell `Get-Content` 对中文文件行号会漂移，行号以 `read`/`grep`（UTF-8）为准。
- 未执行：Hermes 实机批量委派/lifecycle 启动/UI 浏览器渲染（运行时 python ACL 被拒；沙箱禁止 Chromium）。
- 待确认：cron job 是否恒在 gateway 同进程执行（影响"跨 tick 轮询"）；宿主导出 `configuration.md` 与源码/`delegation.md` 的默认并发 3 vs 10 冲突（以上游源码为准）。
- 主要新增证据：`tools/delegate_tool.py`、`tools/delegate_tool_config.py`、`tools/delegate_tool_tasks.py`、`tools/delegate_tool_results.py`、`agent/subagent_lifecycle.py`、`hermes_cli/plugins.py`、`website/docs/user-guide/features/{delegation,cron,kanban}.md`。
