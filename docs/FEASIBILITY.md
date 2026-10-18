# 可行性分析：HERMES Flow 迁移控制面插件

> 结论日期：2026-10-18　|　宿主：Hermes Agent v0.22.2（commit `d923a5e`，`E:\hermes`）
> 证据文档：`research/hermes-capabilities.md`（466 行，全部 `绝对路径:行号`）、`research/loopx-analysis.md`（440 行，GitHub API/raw 原文 + commit `105c4bc`）
> 本文件回答用户的两个问题：**① 需求是否可实现？② 哪些功能 Hermes 已经存在？**

---

## 0. 结论

**可实现，且不需要修改 Hermes 核心代码。** 交付形态是一个标准 Hermes 用户插件（`E:\hermes\plugins\hermes_flow\`）+ 一个 Dashboard 页签（`/flow`）+ 一套领域技能包。

九项需求中：

- **Hermes 原生已具备基础（可直接复用）**：技能体系、子代理调度、持久化（SQLite/JSON）、异常分类与退避、checkpoint/回滚、会话恢复、浏览器验证、cron 调度、Dashboard 插件 UI 框架、LLM 结构化调用。
- **需要插件自研（Hermes 没有）**：① 专家注册表（角色+技能绑定）；② 显式 DAG 工作流引擎；③ **批次调度（拆批/队列/幂等/断点）**；④ 质量评分卡/门控框架；⑤ 结构化经验库；⑥ 面向迁移的控制面 UI（现有插件只有 `board_render` 生成的 HTML 文件，不在 Dashboard 导航中）。
- **需要可选桥接（非阻塞）**：LoopX（外部项目，Apache-2.0；以 CLI+JSON 为稳定契约，不能 import，建议作为可选后端而非唯一内核）。

| # | 需求 | Hermes 原生支持度 | 判定 | 插件补什么 |
|---|---|---|---|---|
| 1 | 自定义 Agent + 技能并自动加载 | 技能=高；专家=中 | ✅ 可实现 | 专家注册表（角色+技能+工具白名单+模型），启动自动加载；技能走原生 `SKILL.md` |
| 2 | 显示已加载的 Agent / 技能 | 高（Dashboard 插件框架原生） | ✅ 可实现 | `dashboard/manifest.json` + 预构建 JS + `plugin_api.py`，新增 `/flow` 页签 |
| 3 | 自定义协作流程 / 工作流 | 中（有 `/goal`、`/loop`、kanban、cron，无 DAG） | ✅ 可实现 | 自研 DAG 引擎 + 调度器 + 模板库 |
| 4 | 可视化工作流进度/Agent 状态 | 高（Dashboard 插件 + WebSocket 能力） | ✅ 可实现 | 运行看板、节点证据、时间轴、实时事件流 |
| 5 | 记忆系统（上下文/历史/偏好） | 高（MEMORY.md/USER.md、FTS5 会话检索、memory provider） | ✅ 可实现 | 结构化经验库（SQLite/FTS5）+ 召回注入（`pre_llm_call`） |
| 6 | 异常处理 + 自循环完成 | 高（错误分类、退避、fallback、checkpoint、`/goal`） | ✅ 可实现 | 工作流级异常分类/断点续跑/租约心跳/turn 预算/自愈循环 |
| 7 | 质量门控 + 打分 + 低分返工 | 中高（`pre_verify`、`hermes verify`、`/goal` gate、browser） | ✅ 可实现 | 五信号评分卡 + 门控状态机 + 回环 + 证据链 |
| 8 | 借鉴/集成 LoopX | 无集成（全仓 0 命中） | ✅ 可实现（可选） | 语义对齐 + CLI 桥接后端，默认自研、失败降级 |
| 9 | **大批量文件拆批 + 子代理循环** | 批量通道原生：`delegate_task(tasks=[...])`（默认 10 并发，超限报错）+ `ctx.subagent_lifecycle`（进程内 8 并发） | ✅ 可实现 | 批次规划（拓扑+预算）+ 批次队列 + 逐批子代理 + 文件级幂等/断点 |

**总体判断：可行（高置信度）。** 预计可上线硬化版 35–50 人日（可演示 MVP 15–18 人日）；最大风险不是"能不能做"，而是"评分模型是否可信"和"长周期运行的环境稳定性"。

---

## 1. 方法与证据分级

- 只读检查本机 `E:\hermes`（运行时数据）、`E:\hermes\hermes-agent`（v0.22.2 源码 + 官方文档）、`E:\hermes\logs`（运行日志）、现有插件 `E:\hermes\plugins\vue3_migration`。
- 外部资料：LoopX 通过 GitHub API + raw 文档原文核验（本机直连 GitHub 被阻断，改用 harness `web_fetch` + 镜像取文）。
- 证据等级：**A** = 本机源码/日志原文（file:line）；**B** = 官方文档原文；**C** = 社区插件/catalog 描述；**D** = 前序产物自称（已逐条核验，有两处被推翻）。

---

## 2. Hermes 已经有什么（能力清单）

### 2.1 底座与扩展点（A 级证据）

| 能力 | 事实 | 证据 |
|---|---|---|
| Agent Loop | `AIAgent` 门面 + `run_conversation` 循环，turn 相位拆分 | `run_agent.py:214`、`agent/conversation_loop.py:1709` |
| 工具系统 | ToolRegistry 自注册 + toolset 分组（file/terminal/browser/memory/skills/delegation/kanban…） | `tools/registry.py:427,666`、`toolsets.py` |
| 插件系统 | `PluginContext`：`register_tool / register_hook / register_middleware / register_cli_command / register_command / register_skill / register_memory_provider / register_context_engine / register_platform …` | `hermes_cli/plugins.py:230,456,633,647,933,937`；`plugins_content.py:22` |
| 插件状态 | `ctx.state`（≤10 MiB JSON）、`plugin_data_dir()/plugin_db()`（WAL SQLite） | `plugins.py:282`；`plugins/plugin_storage.py` |
| LLM 调用 | `ctx.llm.complete / complete_structured`（结构化 JSON schema 校验） | `plugins.py:376`；`plugin-llm-access.md` |
| 子代理 | `ctx.subagent_lifecycle`（launch/wait/status/steer/cancel/result/reconnect）+ `delegate_task` | `plugins.py:386`；`subagent-lifecycle-api.md:15-49` |
| 事件总线 | `ctx.emit / subscribe`（插件命名空间） | `plugins.py:984,1005` |
| 人工审批 | `register_approval_transport`、`inject_message` | `plugins.py:430,603` |
| 自动化模板 | `register_automation_blueprint`（/blueprint + dashboard 画廊） | `plugins_content.py:53` |
| 多实例 | Profile = 独立 `HERMES_HOME`（config/sessions/memory/skills/state.db 全隔离） | `profiles.md:403-410` |

### 2.2 技能体系（A/B 级）

- 标准 `SKILL.md`：`name/description/version/platforms/metadata.hermes.*`，目录 `skills/<category>/<name>/`（`skills.md:194-229,335-358`）。
- 发现优先级：`project > ~/.hermes/skills/ > skills.create_dir > skills.external_dirs`（`skills.md:406-428,467-519`）。
- 渐进披露：`skills_list`（索引）→ `skill_view`（全文）→ 引用文件；系统提示技能索引快照落盘（`prompt_builder.py:1208,1581`）。
- 项目技能需 `hermes skills trust`；技能写入有 `skills.write_approval` 门控。
- 插件技能：`ctx.register_skill(name, path, description, frontmatter)` → 只读 `plugin:skill` 命名空间（`plugins_content.py:22-52`）。

### 2.3 记忆（A/B 级）

| 机制 | 容量/能力 | 结论 |
|---|---|---|
| `memories/MEMORY.md` | **2,200 字符**，纯文本 | 适合零散事实，**不适合**结构化经验库 |
| `memories/USER.md` | **1,375 字符** | 适合用户偏好 |
| `session_search` | SQLite + FTS5 历史会话检索 | 只读历史，不是知识库 |
| Memory Provider | 单例后端（RetainDB/ByteRover/Honcho/Mem0…） | 可换后端，但会顶掉现有 provider；经验库建议插件自建 |
| `pre_llm_call` hook | 每轮注入 `{"context": ...}`（≤10k 字符） | **经验召回的理想注入点** |

### 2.4 异常与恢复（A 级）

- `error_classifier.py:34-66`：**29 种 `FailoverReason`**（覆盖 30+ 语义类别：rate_limit / server_error / timeout / auth / billing / context_overflow / content_policy …），每种带恢复建议（retry/rotate/fallback/compress/abort）。
- `retry_utils.py:30,121,155`：`parse_retry_after_seconds`、`jittered_backoff`（base 5s / max 120s / jitter 0.5）、`adaptive_rate_limit_backoff`。
- 模型 fallback 链；迭代预算（父 500 / 子 250）；上下文预压缩。
- Checkpoint/rollback：影子 git 仓库 `~/.hermes/checkpoints/store/`，写文件/破坏性命令前快照，`/rollback`；**默认关闭**，需 `checkpoints.enabled`（`checkpoints-and-rollback.md:10-57`）。
- 会话恢复：`--resume`/`/resume`，goal/loop 状态存 `SessionDB.state_meta`。
- kanban：stale claim 回收、崩溃 worker 回收（PID+启动指纹）、超限自动 block。

### 2.5 工作流/循环现状（A/B 级）

| 机制 | 形态 | 局限 |
|---|---|---|
| `/goal` | Ralph loop：aux 模型每轮判 done/continue/blocked/wait；completion contract；**确定性 shell 质量门**（先于 judge）；`max_turns=20`；状态可 `/resume` | 单链，不是 DAG |
| `/loop` | 会话内定时/自适应重跑 | 定时器，无状态治理 |
| cron | 后台 job 调度，可挂 skills/scripts | 任务表，无依赖图 |
| kanban | 多 agent 板：列状态机、`task_links` 依赖、dispatch 子进程、review gate、dashboard | **只支持树/链式依赖**；无 fan-out quorum |
| `hermes-workflows`（社区件） | JSON DAG + 后台 runner + fan-out + human/machine gate + fingerprint resume + Desktop DAG 视图 | 第三方独立进程；非迁移领域；无专家注册表/经验库 |
| `vue3_migration`（本机已装） | 自研 DAG + 串行约束 + 质量门 + 恢复 + 经验库 + HTML 看板 | **无 Dashboard 页签**；未用 hooks；无专家/技能注册中心 UI |

### 2.6 质量验证（A/B 级）

- `pre_verify` 钩子：agent 准备收尾且本轮编辑过代码时触发，可 continue/block-stop（`hooks.md:459,823-848`）。
- `hermes verify`：自动探测项目 recipe（bootstrap→build→test→start→readiness→teardown），`--json`（`hermes_cli/subcommands/verify.py:19-45`）。
- `/goal` 质量门：确定性 shell 命令必须 exit 0 才允许 judge 判 done。
- browser 工具 10+（browser_navigate/exec/CDP，多后端）；computer_use；`/review` 评审子代理。
- **没有**统一"评分卡 + 门禁放行"框架 → 插件自研。

### 2.7 UI 扩展（A/B 级，关键可行性依据）

- Dashboard UI 插件三件套：`dashboard/manifest.json` + 预构建 `dist/index.js`（IIFE，`window.__HERMES_PLUGIN_SDK__` / `window.__HERMES_PLUGINS__.register`）+ `dashboard/plugin_api.py`（FastAPI `router`，挂 `/api/plugins/<name>/`）。
- 官方文档：`website/docs/user-guide/features/extending-the-dashboard.md`；先例：`plugins/kanban/dashboard/`（已在本机日志确认挂载成功）。
- **限制**：新增/新启用插件的后端路由由 **hot-mount fallback** 在首次请求时现场挂载（`web_server_dashboard.py:899-973`）；只有已挂载路由的 `plugin_api.py` 代码变更才需重启 web server。前端可用 `/api/dashboard/plugins/rescan` 热重扫；Desktop 是另一套 SDK（`desktop/plugin.js`）。

---

## 3. 九项需求逐条判定

### 需求 1：自定义 Agent + 技能并自动加载 → ✅ 可实现

- **Hermes 现有**：技能原生；"角色"只有 `SOUL.md`/`/personality`/profile/`AGENTS.md`，**没有 Agent 注册表**；`delegate_task` **没有 skills 参数**（只传 goal/context/output_schema）。
- **插件做法**：自建专家 roster（`专家 = 名称 + 角色提示词 + 技能列表 + 工具白名单 + 模型`），启动时从 `plugin_db` + 内置 `agents/*.yaml` 自动加载；派发时把角色提示词与技能摘要写入 `goal/context`（或让子代理 `skill_view("<plugin>:<skill>")`）；技能用 `ctx.register_skill`（内置只读）或写标准 `~/.hermes/skills/`（用户创建，受 write_approval 门控）。
- **风险**：子代理不能自定义 toolset 扩大（继承父），只能收窄；技能注入需控制字符预算（≤10k）。

### 需求 2：显示已加载 Agent/技能 → ✅ 可实现

- **Hermes 现有**：Dashboard 插件框架原生（tab/slots/API）。
- **缺口**：现有 `vue3_migration` 没有 dashboard 三件套，只有 `board_render` 生成 HTML 文件。
- **做法**：`dashboard/manifest.json` 注册 `/flow` 页签 + 纯 IIFE JS（React 由宿主提供）+ `plugin_api.py` 提供 `/api/plugins/hermes_flow/*`。
- **风险**：无构建步骤要求（最终必须是单文件 IIFE JS）；修改已挂载的 `plugin_api.py` 代码需重启 web server（新增插件可由首次请求 hot-mount）。

### 需求 3：自定义协作流程/工作流 → ✅ 可实现

- **Hermes 现有**：无 DAG 引擎；`/goal` 单链、kanban 树状、cron 任务表；社区 `hermes-workflows` 有 DAG（第三方）。
- **做法**：自研轻量 DAG（JSON DSL + 拓扑排序 + 条件/循环/并行/门节点）+ 模板库；已有 `vue3_migration` 的 `Scheduler` 先例。
- **风险**：不要与社区件功能重复造轮子；差异化在迁移领域门控与专家/经验体系。

### 需求 4：可视化工作流进度/Agent 状态 → ✅ 可实现

- **做法**：`/flow` 页签（工作台/编排/监控/质量等 8 屏）+ WebSocket 事件流；状态以内核 SQLite 为唯一事实源，UI 只读投影。
- **风险**：实时一致性；断线重连；大 Run 的渲染性能（虚拟列表/分页）。

### 需求 5：记忆系统 → ✅ 可实现

- **Hermes 现有**：MEMORY.md（2.2k）/USER.md（1.375k）、FTS5 会话检索、memory provider 单例、`pre_llm_call` 注入。
- **做法**：四层记忆；经验库用 `plugin_db`（SQLite FTS5）；召回通过 `pre_llm_call` 注入；偏好双写 USER.md；不顶替 memory provider。
- **风险**：经验噪音（需人工确认/去重/置信度）；注入预算。

### 需求 6：异常处理 + 自循环完成 → ✅ 可实现

- **Hermes 现有**：错误分类、退避、fallback、checkpoint/rollback、会话恢复、`/goal` 自续跑、cron 心跳。
- **缺口**：工作流级 checkpoint + 续跑编排 + 租约/心跳 + turn 预算。
- **做法**：异常分类器映射 `FailoverReason` → 恢复策略；节点级 checkpoint + 幂等写回；租约 TTL + 心跳回收；`flow tick` 每次处理 N 节点/T 分钟后干净退出；driver 三选一（cron / `/goal` / 前台会话）。
- **风险**：上游限流/截断不可完全消除；必须有多级上限与人工门防死循环。

### 需求 7：质量门控 + 打分 + 低分返工 → ✅ 可实现

- **Hermes 现有**：`pre_verify` 钩子、`hermes verify`、`/goal` 确定性门、browser/computer-use、`ctx.llm.complete_structured`。
- **做法**：五信号加权评分（AST/构建/类型/浏览器/行为）+ 硬门 + 回环 + 证据链 + LLM 评审校准 + `pre_verify` 拦截"无验证证据就收尾"。
- **风险**：评分误判；需要抽样复核与权重校准；LLM 评审成本。

### 需求 8：借鉴/集成 LoopX → ✅ 可实现（可选）

- **LoopX 事实**：6,355★ / Apache-2.0 / HEAD `105c4bc`；Python CLI 壳 + TS 控制面；`dependencies=[]` 但**硬需 Node ≥ 22.22.3**；主干 2.0.0a1；**CLI+JSON 是稳定契约**，Python 内核被其架构测试禁止外部 import；官方 DSH 插件不能用于 Hermes。
- **做法（推荐 C 混合）**：默认自研内核（零依赖、可离线），字段/状态机按 LoopX 语义对齐；`--backend loopx` 时通过 CLI 子进程桥接（固定 argv、`--format json`、`loopx doctor` 探测、失败降级、单写者）。不 import、不双写、不复用其 dsh 插件。
- **风险**：版本漂移（1.x→2.0a1）、Node 硬依赖、双权威、Apache-2.0 NOTICE 义务。

### 需求 9：大批量文件拆批 + 子代理循环 → ✅ 可实现

- **Hermes 现有**：两种批量通道——`delegate_task(tasks=[...])` 批量委派（默认 10 并发、可配、**超过上限直接报错**、结果按输入顺序、完成事件持久化但**不恢复崩溃 child**）；`ctx.subagent_lifecycle`（进程内线程池 **8 并发**、可 per-launch `model/allowed_toolsets/correlation_id`、单次 timeout 不支持、需活跃父会话）。两者都不做批次规划/断点续跑。
- **插件做法**：拓扑分层 + 上下文预算装箱 → 批次队列；默认波次串行，同 wave 可并行 2–3；每批 `lifecycle.launch` 一个专家子代理，子代理批内按拓扑序循环处理文件并返回逐文件结构化结果；批次级质量门 + 聚合门；失败只 repair/拆分该批；文件级 `content_hash + attempt_id` 幂等，崩溃后按 hash 续跑。
- **关键约束**：批大小受 32k 字符上下文约束；子代理结果 ≤32k；`delegate_task` 超限报错需切波；`subagent_lifecycle` 池上限 8（插件并发建议 ≤3）；REST 不得直接 launch。
- **结论**：可实现；详细方案见 `research/batch-loop-analysis.md`（A–E 方案对比、批规划算法、状态机、B1–B17 验收）。

---

## 4. 六大缺口（插件必须自建）

1. **专家注册表（Agent Registry）**：Hermes 只有 SOUL/personality/profile；没有"专家→技能→工具白名单→模型/循环策略"的一等对象。
2. **显式 DAG 工作流引擎**：`/goal` 是单链、kanban 是树状、cron 是任务表；跨节点依赖/并行/条件/循环/质量门需要自研。
3. **批次调度（Batch Scheduler）**：Hermes 有批量委派/生命周期子代理，但没有"拓扑分层 + 预算装箱 + 批次队列 + 文件级幂等/断点"的治理层。
4. **质量评分卡/门控框架**：只有零散原语（`pre_verify`、`hermes verify`、`/goal` gate、kanban review），没有"0–100 分 + 阈值 + 回环 + 证据链"的统一框架。
   → 外加 **结构化经验库** 与 **控制面 Dashboard UI**（三件套），共 6 项需自建，其余复用。

---

## 5. LoopX 借鉴与纠偏

### 5.1 值得借鉴

- **控制面与运行时分离**："运行时执行 turn，控制面承载工作"。
- **turn = 受治理的状态转换**，而非计时器；每 turn 有准入（quota should-run）、认领（claim）、回写（update/complete with evidence）、刷新（refresh-state）、结算（spend-slot + receipt 幂等）。
- **单写者 + 租约/版本**；**证据 public-safe**；**危险动作人工门**。
- **状态分层**：registry / goal state / run log / run history / attention queue / quota。

### 5.2 必须纠正的前序错误（实测）

| 前序说法 | 实际情况 | 影响 |
|---|---|---|
| `.loopx/domain-state/<goal>/*.jsonl` 是 LoopX 账本 | LoopX 无此目录；真实为 `.loopx/registry.json` + `.loopx/goals/<goal>/ACTIVE_GOAL_STATE.md`；JSONL 事件溯源已被 PR #5054 退休 | 前序 adapter 是"风格模拟"，不能声称对齐 |
| `dsh plugin add github:loopx-project/loopx` 可作内核 | 对 Hermes 无效；该 URL 被官方 README 否掉；其官方 dsh 插件绑定 DSH Loader/GoalBar | 从方案中删除 |
| "五原语"是 LoopX 术语 | 是前序对 5 个 CLI 生命周期动作的归纳；LoopX 官方模型是"六层存储 + 四种职责 + Turn 契约" | 文档措辞修正，避免误读 |

### 5.3 结论

LoopX 值得**语义借鉴 + 可选桥接**，不值得作为唯一内核（版本漂移 + Node 硬依赖 + 无 Python 公共 API + 双权威风险）。默认自研内核，LoopX 作为 `--backend` 选项，失败自动降级。

---

## 6. 本机运行时现状（先决条件）

**事实**：`E:\hermes\tools\python-3.14.7+20260901-win32-x64\python.exe` 当前 **Access denied / 不可执行**；`hermes.cmd` 硬编码该路径；PM venv 启动器报 `did not find executable` → 当前 `hermes` 全入口不可用。

**但插件系统本身正常**：`agent.log` 记录 2026-10-18 11:01 仍成功完成 `Plugin discovery complete: 56 found, 52 enabled`，并挂载 `/api/plugins/kanban/`、`/api/plugins/hermes-achievements/`；`vue3_migration` 的经验库与 checkpoint 产物仍在。

**修复路径（按优先级）**：
1. `E:\hermes\hermes-agent\setup-hermes.ps1 -RuntimeOnly`（重建 `tools\python` 与工具链）。
2. 修复后 `hermes update` / `hermes pm install`（如仍需）。
3. 临时只读验证可用 `pm-runtime` 的 Python 3.14.7（已实测可 import `hermes_constants`），但不建议长期。
4. 自检顺序：`hermes doctor` → `hermes plugins list` → `hermes plugins doctor vue3_migration --ci` → `hermes dashboard` 看 `/api/plugins/*`。

**结论**：环境问题可修复，不影响方案可行性；但**插件加载/Dashboard 验收必须在修复后进行**。

---

## 7. 替代方案对比（Build vs Buy）

| 方案 | 能力覆盖 | 与需求差距 | 结论 |
|---|---|---|---|
| **装社区 `hermes-workflows`** | DAG、fan-out、human/machine gate、fingerprint resume、Desktop DAG 视图 | 无专家注册表、无迁移领域质量信号、无经验库、英文、独立 runner 进程、gate 用 `wait.until_argv` | 可作参考/共存，不满足 9 项需求 |
| **只用 Hermes 原生 `/goal` + kanban** | 单链自续跑、树状依赖、review gate | 无 DAG、无评分卡、无专家/经验库、无可视化编排 | 不够，但可作为 driver/queue 复用 |
| **改 Hermes 核心** | 完全定制 | 违反插件契约（插件不得猴补核心）、升级即坏 | 否定 |
| **自研 HERMES Flow 插件（推荐）** | 9 项全覆盖 | 开发量 35–50 人日（MVP 15–18）；质量模型需调优 | ✅ 推荐 |

---

## 8. 最终结论与建议

1. **可实现**：9 项需求均有明确实现路径，Hermes 已提供底座/扩展点/持久化/恢复/UI 框架，插件补 6 个缺口即可（含批次调度）。
2. **建议分两阶段**：
- **阶段 A（可演示 MVP，约 15–18 人日）**：专家/技能注册 + DAG 引擎 + **批次循环** + Dashboard 8 屏（读多写少）+ 质量门 + 异常恢复 + 样例 E2E。
   - **阶段 B（硬化，约 20–32 人日）**：租约/心跳、WebSocket、经验召回注入、人工门、LoopX 可选后端、安全、性能与完整测试。
3. **先修运行时**：`setup-hermes.ps1 -RuntimeOnly`，否则无法做加载/UI 验收。
4. **评测先行**：先定义"什么算迁移成功"的评分基线（样例项目 20 文件），再谈自动回环，避免"自动跑但不可信"。
5. **不追求一次替代 LoopX**：默认自研内核，LoopX 可选；等真实痛点（多 harness、跨项目审核面）出现再切换。

---

## 附录：证据索引

| 主题 | 文件 |
|---|---|
| Hermes 架构/插件/技能/记忆/恢复/质量/运行时（全部 file:line） | `research/hermes-capabilities.md` |
| LoopX 仓库事实、状态模型、CLI、集成方案、前序纠偏 | `research/loopx-analysis.md` |
| 产品需求、UI、实现方式、验收标准 | `docs/PRD.md` |
| UI 设计稿与规范 | `ui-design/index.html`、`ui-design/design-spec.md`、`ui-design/screenshots/` |
| 批量循环调研与设计（方案 A–E、算法、B1–B17 验收） | `research/batch-loop-analysis.md` |
| 前序可运行内核（123 单测） | `E:\DHLocal\HERMES\vue3migrate-core`（只读参考） |
