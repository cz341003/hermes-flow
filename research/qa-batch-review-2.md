# 批量拆批 + 子代理循环：第三轮增量复审（最终收尾）

> **评审对象（2026-10-18 14:26–14:31 快照）**：
> - `docs/PRD.md` v2.2（约 1,467 行 / 14:25:52）；`docs/FEASIBILITY.md`（14:25:52）；`research/batch-loop-analysis.md`（611 行 / 14:24:14）
> - **UI 最终冻结版**：`index.html` **318,049 B / 14:29:06**；`design-spec.md` 28,657 B / 14:29:06；`PROMPTS.md` 26,278 B / 14:29:06；`overview.html` 2,930 B / 13:23:55（静态画廊，引用截图路径）
> - `screenshots/`：`00` 14:29:19、`07` 14:29:17（晚于最终 index）；`01` 14:27:38、`02` 14:26:01、`03` 14:27:35、`04` 14:27:17、`05` 14:27:53、`06` 14:27:20、`08` 14:27:40（早于最终 index，见 §5）
> **评审方式**：只读核对源码/文档 + 交叉比对 + `read_image` 复核截图；未修改交付物。

---

## 0. 最终结论

**P0 = 0｜P1 = 1｜P2 = 15 → 有条件放行（Conditional Release）。**

- **7 项 P1 中 6 项闭环**（P1-1/2/4/5/6/7）；**P1-3（staging_apply 写入闭环）部分闭环**，仍有两处执行语义未定义（见 §2），建议补完后再开工。
- 其余均为文档/四件套一致性与实现细节 P2，不阻塞放行。
- **Gate**：① 修 P1-3 两处；② 截图与最终 index 的版本一致性需重渲或书面记录变更范围；③ "多批循环"降为 P2 实验需用户确认（若用户坚持多批为 P0，则缺口回到 P1）。

---

## 1. 七项 P1 闭环核对

| # | P1 | 状态 | 核对证据 |
|---|---|---|---|
| 1 | batch 配置 schema 三套 → 统一 | ✅ 闭环 | `PRD.md:337` FR-3 唯一 schema 声明 + 旧字段 deprecated；`PRD.md:630-638` §8.1 DSL 已改 `source/order/adaptive/context_budget_chars/.../write_mode`；`PRD.md:676-681` §8.4 与 `:1397-1430` 附录 G 同构；analysis `:187-198` 同步。仅遗留 `write_scope` 旧字段（P2-2） |
| 2 | 结构化契约（lifecycle 无 output_schema） | ✅ 闭环 | `PRD.md:572`（lifecycle 无 output_schema→提示词+插件校验+一次格式纠正重派）、`:573`（delegate 原生 output_schema/summary 24k）、`:787-788` 通道差异表；`PRD.md:610` B13；analysis `:369-371`；`subagent_lifecycle.py:48-62,120` 与 `delegate_tool.py:730-732` 一致 |
| 3 | 写入/幂等（staging_apply） | ⚠️ **部分闭环** | `PRD.md:557` write_mode、`:577` 只写 staging、`:588` 越界写拒绝、`:593` base_hash/applied_hash/UNIQUE、`:609` B11/B12；`PRD.md:1156-1160` batch_items 新增 4 列 + UNIQUE(group_id,file_path)；analysis `:23,298,381,397,405` 同步。**残留见 §2** |
| 4 | 调度/租约（driver 单例 + wait 分片） | ✅ 闭环 | `PRD.md:570` Run 级 driver 单例锁 + 30s heartbeat；`:575` wait ≤60s + 跨 tick handle 1h + applied_hash 对账；`:576` `tick_budget_seconds=600`；`:610` B14；analysis `:274,313-316`；lifecycle 句柄/结果保留 1h（`subagent_lifecycle.py:29`）已一致 |
| 5 | 结果上限 32k vs 24k | ✅ 闭环 | `PRD.md:573,787`（lifecycle 32k / delegate summary 24k）、B9 `:607`；附录 G `:1459-1461` 证据行号已改 `delegate_tool_config.py:17,21,151-167`、`delegate_tool_results.py:160,163,166,275-277`；analysis `:60,65-67,98` 同。源码核对：`delegate_tool_results.py:160 DEFAULT_MAX_SUMMARY_CHARS=24000`、`subagent_lifecycle.py:26-28` 32k |
| 6 | 多批语义 | ✅ 闭环（范围冻结） | `PRD.md:554-555`：P0 仅 `per_batch/single_file`、`max_batches_per_launch=1`；`persistent_child` 降 P2 实验（≤3 批/child，B15 `:611`）；analysis `:118,379` 同。**需用户确认"多批循环"可接受 P2**（见 §6） |
| 7 | 三层门控 + 隔离 SLO | ✅ 闭环（PRD/analysis） | `PRD.md:879-890` §11.4 三层（批级 AST/diff+白名单硬门；wave 可选增量；聚合级全量 build/type/browser）；`:595` 摘要；`:610` B16；`:1238` 隔离 SLO 改为"同 wave 100%，依赖批按策略阻塞（预期）"；analysis `:429-432,507` 同步。design-spec §3.6 与 FR-7 仍有旧表述（P2-4/3） |

---

## 2. 剩余 P1（1 项）：staging_apply 的"执行闭环"仍有两处空白

### P1-1　staging_apply 只验证了 staging 集合，未验证/阻止 child 直接写工作区；Batch Packet 还缺工作区定位信息
- **a) 越界写仍依赖 child 自觉**：PRD `:557,577,588,789` 与 analysis `:23,381,405` 都声明"child 只写 staging、插件校验 staging 集合 ⊆ 批内文件后备份并原子应用"；但 child 仍拥有 file/terminal 工具，`working_directory=staging` 只是 cwd，不是沙箱（`SubagentLaunchRequest.working_directory` 见 `subagent_lifecycle.py:56`，无路径级限制；`allowed_toolsets` 只能按 toolset 收窄）。若 child 用绝对路径/`cd` 直接写工作区其他文件，插件当前只检查 **staging 目录内容**，不会发现工作区改动；`B11 越界写被拒绝并回滚` 因此只能测"staging 里多写了文件"，测不到"绕过 staging 直写工作区"。
  - **修法**：launch 前对工作区做基线指纹（或 `git status --porcelain` 快照）→ child 结束后做工作区 diff/哈希对比 → 非 staging 产生的改动一律回滚 + `FLOW_BATCH_WRITE_SCOPE` + 人工门；B11 增加"child 尝试直接写批外文件/工作区文件"的用例。
- **b) Batch Packet 无法定位源文件**：analysis §6.2 Packet（`:320-350`）只有相对 `files[].path`、`staging_dir: "plugin-data/..."`（相对路径）、无 `project_root`；而执行时 `working_directory=str(staging)`（analysis `:286`）。child 在 staging cwd 下读相对路径 `src/...` 会指向 staging 内不存在的文件；analysis `:375` 却又要求"读工作区文件 → 写 staging 副本"，两处矛盾。
  - **修法（择一）**：① 插件在 launch 前把批内源文件按相对路径预拷贝到 staging，child 只在 staging 读/写，插件 apply 时整体替换（推荐，最干净）；② Packet 增加 `project_root`（绝对路径）+ `files[].abs_path`，明确 child 读工作区、写 staging 的契约。并把 `staging_dir` 改为绝对路径。

> 这两点是**同一 P1 修复的闭环缺口**，建议合并为一次修订：`Packet 增加 project_root/absolute paths（或预拷贝）` + `工作区基线 diff 校验 + 回滚` + `B11 用例扩展`。

---

## 3. 剩余 P2（15 项，不阻塞）

1. **B 编号不齐**：PRD `:599` 标题"B1–B16"但 `:612` 含 B17；附录 G 尾注 `:1467` 写"B1–B16"；analysis `:488/552` 写"B1–B16"；FEASIBILITY `:170/:254` 仍写"B1–B10"。统一为 B1–B17。
2. **`write_scope` 旧字段残留**：`PRD.md:694`（§8.4 DSL）与 `:1429`（附录 G）仍带 `"write_scope":"batch_files_only"`，而 FR-3 `:337` 的官方 schema 无此字段、deprecated 清单只列 `glob/batch_size/parallel`。删除或列入 deprecated。
3. **FR-7 未加批次例外**：`PRD.md` FR-7 仍写"硬门：构建失败或浏览器白屏直接不通过"，未引用 §11.4；建议加一句"batch 节点按 §11.4 分层门控（批级仅 AST/diff，全量硬门在聚合级）"。
4. **design-spec §3.6 门控表述旧**：`design-spec.md:143` "质量门 | 每批五信号 + 全量聚合门"与 PRD §11.4 三层门控冲突；应按 PRD 改为"批级 AST/diff、聚合级五信号+全量"。
5. **design-spec 结果上限表述**：`design-spec.md:138` "上下文预算 28,000 chars / 批（≤32,000 结果上限）"未区分通道（delegate summary 24k）；建议改为"context 32k（lifecycle）/ result 32k lifecycle、24k delegate"。
6. **design-spec API 缺批次写回端点**：`design-spec.md:307-315` 只有 batches GET/items/retry/split，缺 PRD §14.5 新增的 `POST /batches/{id}/ingest` 与 `/apply`；四件套需同步。
7. **repair/split 与 UNIQUE 语义未定义**：`batch_items UNIQUE(group_id,file_path)`（`:1156-1160`）与"repair 子批（只含失败文件）/split 子批"（`:589`、analysis `:432`）存在冲突风险——repair 新批次再插同 (group,file) 会违反唯一键；需明确"复用同一 batch_items 行、更新 batch_id/attempt"或把唯一键改为 `(group_id,batch_id,file_path)`。
8. **原子应用的文件系统前提未写**：staging 位于 `plugin-data/hermes_flow/staging/...`（analysis `:336`），项目在任意盘符；Windows 下跨卷 `os.replace` 非原子，且"备份原文件"位置/保留期/清理未定义。建议：staging 放项目同卷临时目录，或"复制到目标目录临时名 + 同卷 replace"，并定义备份保留策略。
9. **driver 锁的 TTL/释放/续租细节**：`PRD.md:570` 只说"Run 级租约锁 + 30s heartbeat"，未定义 holder 过期、进程崩溃释放、获取失败退避；cron job 与 handle 1h 保留的进程模型仍"待确认"。
10. **聚合门覆盖率与 manual 冲突**：§11.4 `:890` 聚合门要求覆盖率 100%（无 pending/failed），但 manual 是合法批次终态（`:593`）；manual 文件按何口径计入覆盖率/是否需人工豁免未定义（B2 写"覆盖率 100%"）。
11. **并行 worktree 的合并/写回语义**：`PRD.md:556`/B8 要求并行批用独立 worktree，但未定义各 worktree 的 staging 合并顺序、对主工作区的 apply 串行化、以及 build/browser 并发端口冲突；建议明确"apply 串行 + merge 冲突人工"。
12. **`batch_items` 状态枚举不一致**：PRD `:593` 用 `applied|manual`；design-spec §3.6 与 UI 用 `pending/running/done/failed/manual`；需统一（建议 `pending|running|applied|failed|manual`，`done` 为批次态）。
13. **FEAS 结果上限口径**：`FEASIBILITY.md:168` 仍写"子代理结果 ≤32k"（未区分 delegate 24k）。
14. **B9 表述混通道**：`PRD.md:607` "context ≤32,000、结果 ≤24,000（delegate 通道）"——lifecycle 结果 32k 未写，易误读；建议拆成两条。
15. **UI 截图与最终 index 的版本一致性**：最终 index 14:29:06；`00`/`07` 14:29:19/14:29:17 晚于它，但 `01`(14:27:38)、`02`(14:26:01)、`03`(14:27:35)、`04`(14:27:17)、`05`(14:27:53)、`06`(14:27:20)、`08`(14:27:40) 均**早于**最终构建。Lead 说明"02 最后改动仅 07 相关、内容一致"，但未覆盖其余 6 张；建议重渲这 6 张，或书面记录 14:29:06 变更范围（仅 quality/overview）以证明内容等价（Gate）。

---

## 4. UI 最终版复核（按 Lead 指定项）

| 检查项 | 结果 | 证据 |
|---|---|---|
| 07 门控审计完整可见 | ✅ 可见 | `07-quality.png`（14:29:17）：右下"门控审计"面板含"最近审查 17:20:52 / 审查人 齐 / 权重 20/25/15/25/15 + 1 条日志（TreeSelect.vue 64 < 70 → 回环 #2）"；5 个 KPI（含"批次通过率 92.0% · 18 批完成"）；文件表含"批次"列（#18/#15/#16 等） |
| 02 批次队列/证据 Tab | ✅ 可见 | `02-monitor.png`（14:26:01）：左列"批次队列 18/43"按 WAVE 3/WAVE 2 分组（#19 planned/#18 running/#17 gated 人工门/#16 done/#15 split），可展开批内文件；中列"执行时间轴 batch events"+调度日志 batch.claim/ingest/gate/split/retry；右列证据链 Tab=构建日志/diff/截图/**批次**，批次 tab 显示 `batch-18.summary.json` 与 7 文件 done/failed/pending；底部 tick 10 批/并发 1/预算 28k/拆分≤2 层 |
| 01 批次进度 | ✅ 可见 | `01-workbench.png`（14:27:38）：目标 287 / 已转化 126（43.9%）/ "43 批次 · 单批 7 文件"；当前运行"批次 18/43"；"批次循环"双进度条（批 42% / 文件 44%）；页脚 18/43 批次、126/287 文件 |
| 03 循环徽标 | ✅ 可见 | `03-agents.png`（14:27:35）：代码转化专家卡"循环 · 7 文件/批"徽标 + 细进度 + "批次 18/43"；8 registered · 8 enabled；筛选 2/4/1/1 |
| 05 批次节点/属性 | ✅ 可见 | `05-flow.png`（14:27:53）：代码转化节点 `×43 批` + "批次 18/43 · 7 文件/批"；属性面板"批量执行"区（批量源 report:deps.files·287 文件 / 批大小 7 / 并发批次 1·波次串行 / 内层循环 serial·批内拓扑序 / 失败拆分 2 层 / 每批质量门 ON·28,000）；左下"批次预览 #14 done #15 split #16 done #17 gated #18 run · +38" |
| 08 批量执行面板 | ✅ 可见 | `08-settings.png`（14:27:40）："批量执行"面板（默认批大小 7、最大并发批次 1·波次串行、每 tick 10、单批等待 1800s、拆分深度 2、上下文预算 28,000 chars）+ 生效配置 JSON `batch {size:7, conc:1, tick:10}`；SQLite Kernel v0.8.4 默认；权重 20/25/15/25/15 |
| 四件套同源 | ⚠️ 部分 | index/design-spec/PROMPTS 均为 14:29:06（同步）；00/07 截图晚于该构建；其余 7 张更早（见 P2-15）。design-spec §3.6/§4/§8.5 已含批次，但 API 缺 ingest/apply（P2-6）、门控表述旧（P2-4） |

> 另：`overview.html` 本身为 13:23:55 静态画廊，图片引用会随 screenshots 更新；无需重写，但若要"四件套同源"也应把 overview 的生成时间纳入说明。

---

## 5. 放行建议

- **结论**：**P0=0，P1=1，P2=15**；修完 §2 的 staging 闭环（1 处修订 + B11 用例）并处理 P2-15 的截图版本说明后，可放行进入实现。
- **必须**：P1-1（Packet 工作区定位 + 工作区基线 diff/回滚 + B11 扩展）。
- **放行记录**：P2-15（6–7 张截图早于最终 index）重渲或书面记录 14:29:06 变更范围；P2-6（design-spec API 补 ingest/apply）、P2-4（design-spec 门控表述）、P2-1（B1–B17）建议随交付说明一起修。
- **需用户确认**：P1-6 的"多批循环"已明确降为 P2 实验；若用户坚持 P0 多批循环，则该缺口回到 P1（需 child 内多批 checkpoint + 独立验收）。
- 其余 P2 可并行清理，不影响实现启动。

---

## 6. 核验方法与局限

- 只读核对：PRD/FEAS/analysis 交叉比对；Hermes 源码/官方文档 20+ 处（`delegate_tool_config.py:17,21`、`delegate_tool_results.py:160`、`subagent_lifecycle.py:25-28,120,159-160,228,277-280`、`plugins.py:674-683`、`delegation.md:211,219-233,342-380`）。
- 未执行：真实批量委派/lifecycle 启动/浏览器渲染（沙箱限制，截图由 Lead 代渲）。
- 截图复核：9 张逐张 `read_image`；重点核对 07/02/01/03/05/08 的批次元素与数值（43/7/18/126/287/28k/1800s）。
- 时间戳事实：最终冻结 index/design-spec/PROMPTS = **14:29:06**；`00` 14:29:19、`07` 14:29:17 晚于冻结；其余 7 张 14:26:01–14:27:53 早于冻结。

---

# 第三轮补丁复核（P1-1 闭环确认，2026-10-18 14:32–14:34）

> 仅核验 Lead 声明的 P1-1 补丁与同步 P2，不再重审全文。
> 快照：`PRD.md` 121,566 B / 14:31:49；`batch-loop-analysis.md` 46,199 B / 14:32:03；`design-spec.md` 28,879 B / **14:31:55**；`index.html` 318,049 B / **14:29:06（冻结）**；`PROMPTS.md` 14:29:06；9 张截图 **14:32:11–14:32:30**（全部晚于冻结 index）。

## F1. 结论

**P1-1 已闭环（机制层面）；P0 = 0，P1 = 0。可放行。**

- **Packet 绝对路径** ✅：`PRD.md:579`（`project_root` 只读源、`staging_root` 可写、每文件 `source_path/staging_path`、`working_directory=project_root`）；`PRD.md:798` Packet 字段总表；analysis `:331-338` Packet 示例含 `project_root/staging_root/files[{path,source_path,staging_path,hash}]/write_policy`；`PRD.md:794` 与 analysis `:373,406` 一致。
- **工作区基线 + 越界检测** ✅：`PRD.md:580-581`（启动前 `git status --porcelain + git diff --name-only` 或 hash 快照写入 `batches.workspace_baseline_json`；结束后 `post - pre - 批内文件` 非空 → 回滚 + `agent_drift` + `FLOW_BATCH_WRITE_SCOPE` + 人工门）；`PRD.md:1158` 表字段已加 `workspace_baseline_json`；`PRD.md:1181` 越界审计、`:1182` 并行批 **apply 串行化**、冲突转人工；analysis `:406-409` 同步；错误码 `FLOW_BATCH_WRITE_SCOPE` 在 `PRD.md:1357`。
- **B11 可测性**：⚠️ 机制可测（工作区基线审计），但 analysis 的 B11 用例（`:510`）仍只写"child 在 staging 写批外文件"，**未写"child 直接写工作区批外文件"** 这一关键用例；PRD B11（`:614`）为通用表述。属文档用例补充（P2），不影响机制成立。
- **同步 P2**：B 编号统一 ✅（PRD `:604,617,1475`；analysis `:561`）；design-spec §3.6 门控改为"批级 AST/diff + 白名单；wave 可选增量；全量只在聚合门"（`design-spec.md:143`）✅；API 补 `ingest/apply`（`design-spec.md:316-317`）✅；`write_scope` 已从附录 G 移除（仅 §8.4 DSL 残留，见下）⚠️；覆盖率/manual 口径、并行 apply 串行化 ✅；截图全部 14:32 重渲 ✅。

## F2. 仍建议顺手修（P2，不影响放行）

1. **analysis §6.1 伪代码残留**：`:286` 仍 `working_directory=str(staging)`，与新正文"child cwd=project_root"（`:373,406`；PRD `:579`）矛盾；按伪代码字面实现会重现"staging 下读不到源文件"。改成 `working_directory=packet.project_root`（staging 仅作写路径）。
2. **B11 用例补直写工作区**：analysis `:510` 增加"child 用绝对路径写 project_root 下批外文件 → 工作区审计发现 → 回滚 + `FLOW_BATCH_WRITE_SCOPE` + 人工门"。
3. **`write_scope` 残留**：`PRD.md:699`（§8.4 batch DSL 示例）仍有 `"write_scope":"batch_files_only"`；Lead 称已移除，建议删除或列入 deprecated（附录 G 已删）。
4. **FEAS 编号未同步**：`FEASIBILITY.md:170,254` 仍写"B1–B10"，建议改为 B1–B17。
5. **design-spec 事件列表**：`:165` 日志标签仍列 `batch.claim/ingest/gate/split/retry`，缺 `batch.apply`（§3.6 `:141` 已含）；建议同步。
6. **上一轮未复核的 P2 仍在**（本轮未改，不阻塞）：staging 跨卷原子替换/备份保留策略、repair/split 与 `UNIQUE(group_id,file_path)` 的行复用语义、driver 锁 TTL/释放细节、聚合覆盖率与 manual 豁免口径。

## F3. 放行判断

- **可放行**：P0=0、P1=0；P1-1 的两条修法均已落到 PRD/analysis（Packet 绝对路径 + 工作区基线/越界审计/回滚/串行 apply），B11 机制可测。
- **放行记录**：建议把 F2-1（analysis 伪代码 cwd）与 F2-2（B11 直写用例）作为实现前的一行修订；其余 F2 可作为文档清理项随实现并行。
- **截图一致性**：index 冻结 14:29:06；9 张截图 14:32:11–14:32:30，全部晚于冻结构建 ✅；design-spec 14:31:55、PRD/analysis 14:31:49–14:32:03 为最后一轮同步。
