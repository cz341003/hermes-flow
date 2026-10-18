# HERMES Flow 产品需求文档（PRD）

> **产品名**：HERMES Flow（赫尔墨斯工作流控制面）
> **插件 ID**：`hermes_flow`　|　**宿主**：Hermes Agent v0.22.2（Nous Research，Python）
> **版本**：v2.2（Draft for Review，新增 FR-10 批量循环）　|　**日期**：2026-10-18　|　**作者**：Agent Teams（Lead + hermes-analyst / loopx-analyst / ui-designer）
> **关联文档**：`docs/FEASIBILITY.md`（可行性）、`research/hermes-capabilities.md`（Hermes 能力证据）、`research/loopx-analysis.md`（LoopX 研究）、`ui-design/design-spec.md`（设计规范）、`ui-design/index.html`（可交互设计稿）
> **首个落地场景**：大型 Vue2 项目 → Vue3 + Pinia + Vue Router 4 + Vite 的批量迁移（200–500 文件、约 100+ 批次、依赖图串行）

---

## 0. 一句话定位

**HERMES Flow 是架在 Hermes Agent 之上的「长周期多智能体工程控制面」**：把「角色提示词 + 技能」注册成可复用的 Agent 专家，把专家协作编排成可视化 DAG 工作流，用持久化状态内核（借鉴 LoopX 五原语）驱动一轮轮受治理的 turn，配合异常自愈、质量门控与经验沉淀，让"几百步、跨多次运行、需要质量把关"的工程任务像被管理的数字员工团队一样持续推进——**最少人工介入、最多可验证产出**。

> 它不是重写 Hermes，而是补上 Hermes 缺的「控制面」层：
> `Hermes 运行时（执行 turn）` + `HERMES Flow（承载工作：状态/编排/门控/记忆）`。

---

## 1. 背景与问题

### 1.1 业务背景

用户维护一个大型 Vue2 工程，技术栈为 **Vue2 + Vue Router 3 + Vuex + Webpack + Less + Ant Design Vue + jQuery 插件（如 ztree）**。目标是升级到 **Vue3 + Pinia + Vue Router 4 + Vite**。

这不是"改几个文件"的任务，而是：

| 维度 | 规模/复杂度 |
|---|---|
| 文件数 | 200–500 个 `.vue/.js/.less`，18–30 个目录 |
| 批次 | 依赖图决定了约 100+ 个可执行批次（组件 → 页面 → 路由/Store → 入口） |
| 迁移点 | Options API、filters、mixins、`this.$xxx`、Vuex→Pinia、Router3→4、webpack→vite、less 变量、antdv 1.x→4.x、jQuery 插件替代 |
| 验证 | AST/编译、`vite build`、`vue-tsc`、浏览器渲染与交互、与源组件行为一致性 |
| 周期 | 数天到数周，跨多次会话/多次运行 |

### 1.2 现有工作方式的六个痛点

1. **上下文膨胀与注意力衰退**：主 Agent 连续处理几十个文件后开始"忘记"串行约束，出现并行违规、漏改、重复改。
2. **异常即中断**：API 限流（429）、输出截断、超时一旦发生，任务停在半路，需要人工判断"从哪继续"，经常重头再来。
3. **质量不可控**：文件"看起来改完了"但没有客观评分，问题在浏览器里才暴露，返工成本高。
4. **经验不沉淀**：同一个坑（如 ztree、`this.$refs` 时序、less 变量注入）在不同文件/不同会话重复踩。
5. **过程黑盒**：跑到第几步、每个专家在干什么、哪些节点失败、为什么低分，全靠翻日志。
6. **协作不可编排**：想让"分析专家→依赖专家→转化专家→质量专家→验证专家→修复专家"按顺序协作，只能靠人肉在对话里指挥。
7. **文件量太大**：200–1000 个文件不可能塞进一个子代理的上下文；一次性全量处理必然截断/质量衰减，失败一次就整段重来。**必须拆成批次、每批一个子任务、由子代理循环完成**（本 PRD v2.2 新增 FR-10）。

### 1.3 已有基础（本机现状，2026-10-18 核实）

| 资产 | 位置 | 状态 | 价值 |
|---|---|---|---|
| Hermes Agent v0.22.2 | `E:\hermes`（源码 `E:\hermes\hermes-agent`） | 已安装；**`tools\python-3.14.7...` 当前被 ACL 拒绝/不可执行，`hermes` 全入口暂不可用（需 `setup-hermes.ps1 -RuntimeOnly` 修复）**；日志证明插件系统曾正常加载 52/56 | 宿主运行时、技能/插件/Dashboard/子代理/记忆/cron/browser 等原生能力 |
| 前序迁移插件 `vue3_migration` | `E:\hermes\plugins\vue3_migration` | 已存在，16 个工具 + 1 CLI | 已验证：DAG 串行硬约束、质量评分、异常恢复、经验库、HTML 看板 |
| 共享内核 `vue3migrate_core` | `E:\DHLocal\HERMES\vue3migrate-core` | 123 个单测通过 | 状态内核/引擎/质量/恢复/经验/LoopX 风格适配器，可直接复用 |
| 迁移技能包 | `E:\hermes\skills\migration\`（7 个 SKILL.md） | 已落地 | 六阶段专家技能 + 入口技能 |
| 端到端样例 | `E:\DHLocal\HERMES\sample-app`（20 文件 Vue2） | 已跑通 | 离线验收样例 |
| 前序 UI 原型 | `E:\DHLocal\HERMES\ui-mockup\index.html` | 单文件 7 屏 | 信息架构参考（本 PRD 要求重做视觉/交互） |

**结论：不是从零开始。** v2.2 的增量价值是：把"领域专用脚本式插件"升级为**通用的 Agent/Skill 注册中心 + 工作流编排 + Dashboard 控制台 + 自治闭环**，并把前序内核沉淀为可复用基础。

---

## 2. 目标与非目标

### 2.1 产品目标（可验收）

| # | 目标 | 验收口径 |
|---|---|---|
| G1 | **专家与技能一键注册、自动加载** | 粘贴一段角色提示词 → 3 步内生成专家卡片；重启 Hermes 后专家/技能/绑定关系自动恢复；专家可绑定 0..N 个技能 |
| G2 | **可视化编排自定义协作流程** | 画布上拖拽/连线生成 DAG；保存前做环/悬空边/无入口校验；支持串行、并行、条件、循环、质量门、人工门 |
| G3 | **运行时全景可观测** | Dashboard 实时显示：当前步骤、每个专家状态（空闲/运行/等待/成功/失败/回环）、整体进度、节点耗时/重试/评分、证据流；刷新/重开不丢状态 |
| G4 | **自治闭环（无需人工介入）** | 限流/截断/超时/进程重启后自动续跑；单节点重试上限内自愈；超过上限才升级人工门；连续运行 2 小时无人值守不中断 |
| G5 | **质量门控与低分回环** | 每节点五信号评分（AST/构建/类型/浏览器/行为）；≥85 通过、70–84 警告、<70 回环修复；≤3 轮，超限人工门；评分与证据可追溯 |
| G6 | **记忆与经验沉淀** | 坑位经验结构化入库、去重计数、按阶段/关键词召回并注入下一轮；重复坑位二次出现率显著下降；用户偏好持久生效 |
| G7 | **借鉴 LoopX 的状态治理** | Goal/Todo/Turn/Gate/Evidence/Quota/Checkpoint/Receipt 语义完整；内核可切换（自研 SQLite / LoopX 适配）且上层无感知 |
| G8 | **与 Hermes 原生能力无缝集成** | 以标准 Hermes 插件形态交付（`plugin.yaml` + `register(ctx)` + dashboard tab + CLI），不修改 Hermes 核心代码 |
| G9 | **大批量分批循环** | 287 文件自动切成约 43 批；每批一个子任务、绑定一个专家；批内循环、批间串行（可选同层并行）；失败只重跑该批/该文件；断点精确到文件；1000 文件规模可验收 |

### 2.2 非目标（本期不做）

- **不做代码转换器本身**：语法转换由"专家 + 技能 + 子代理"完成，插件只做治理与验证编排（前序内核里的确定性转换器仅用于离线演示/兜底）。
- **不替代 Hermes 运行时**：不自己实现 LLM 调用循环、不接管工具执行。
- **不做云端多租户 SaaS**：本地优先、单机多 profile。
- **不自动合并/发布/删除**：危险动作永远走人工 Gate（对齐 LoopX "把判断留给人"）。
- **不做通用 BI/报表平台**：质量报告只服务迁移治理。

---

## 3. 可行性结论（先回答"能不能做、Hermes 有没有"）

> 详细证据见 `research/hermes-capabilities.md`（每项含 `文件:行号`）与 `research/loopx-analysis.md`（含仓库 URL/commit）。

### 3.1 结论：**可实现（高置信度）**

九项需求全部有成熟实现路径；其中 **6 项能力需插件补足**（专家注册表、DAG 引擎、批次调度、质量评分卡、结构化经验库、控制面 UI），其余复用 Hermes 原生能力，没有"必须改 Hermes 核心"的硬阻塞。

| # | 需求 | Hermes v0.22.2 原生现状 | v2.2 实现路径 | 结论 |
|---|---|---|---|---|
| 1 | 自定义 Agent + 技能并自动加载 | 技能体系原生（`SKILL.md` 发现/加载/信任/命名空间）；角色可由提示词 + 技能承载；**无一级公民的 Agent 注册表** | 插件新增 Agent/Skill Registry（SQLite + JSON），启动时自动加载；技能落盘为标准 `SKILL.md` 并注册 | ✅ 可实现（插件补注册表） |
| 2 | 显示已加载的 Agent/技能 | Dashboard 插件体系原生支持自定义页签/插槽 + 后端 FastAPI 路由 | 新增 `dashboard/manifest.json` → `/flow` 页签，展示专家/技能库 | ✅ 原生支持 UI 扩展 |
| 3 | 自定义协作流程/工作流 | 无显式 DAG 引擎；有 `delegate_task`、`ctx.subagent_lifecycle`、cron、kanban | 插件内实现 DAG 引擎 + 调度器 + 租约/心跳 | ✅ 可实现（自研引擎） |
| 4 | 可视化工作流进度 | Dashboard tab 可读插件 API；kanban 插件是同构先例 | `/flow` 内做看板/DAG 运行态 + WebSocket 事件流 | ✅ 原生支持 + 自研视图 |
| 5 | 记忆系统（上下文/历史/偏好） | 原生双层记忆（MEMORY.md 2,200 字符 / USER.md 1,375 字符）、FTS5 会话检索、memory provider 插件、`pre_llm_call` 每轮注入（≤10k 字符） | 四层记忆：turn 切片 → run 状态 → 经验库（SQLite FTS5）→ 偏好；`pre_llm_call` 注入召回 | ✅ 可实现（扩展经验层，不顶替 provider） |
| 6 | 异常处理 + 自循环完成 | `error_classifier`（29 种 FailoverReason）、`retry_utils`（Retry-After/jitter/自适应限流）、模型 fallback 链、checkpoint/rollback、`/goal` 自续跑、cron 心跳 | 异常分类器映射原生语义 + 节点级 checkpoint + 租约/心跳 + turn 预算 + 自愈循环 | ✅ 可实现（自研恢复编排，复用原生重试） |
| 7 | 质量门控 + 打分 + 低分返工 | `pre_verify` 钩子（无验证证据不许收尾）、`hermes verify` recipe、`/goal` 确定性 shell 门、browser/CDP、`ctx.llm.complete_structured`；**无统一评分卡** | 五信号评分 + 门控状态机 + 硬门 + 回环 + 证据链 + LLM 评审校准 | ✅ 可实现（自研门控引擎） |
| 8 | 借鉴/集成 LoopX | 未集成；LoopX 为独立控制面项目（详见研究文档） | 五原语语义对齐 + 可切换 adapter（自研 SQLite 默认 / LoopX 可选） | ✅ 可实现（可选增强） |
| 9 | **大批量文件拆批 + 子代理循环** | 原生两种批量通道：`delegate_task(tasks=[...])` 批量（默认 10 并发，超限报错）与 `ctx.subagent_lifecycle`（进程内 8 并发，可 per-launch model/toolsets）；均无崩溃续跑 | 插件实现批次规划（拓扑分层+预算装箱）+ 批次队列 + 逐批生命周期子代理 + 文件级幂等/断点；`delegate_task` 波次作为加速/降级 | ✅ 可实现（详见 `research/batch-loop-analysis.md`） |

### 3.2 三个关键可行性依据（必须知道的底层事实）

1. **UI 不是瓶颈**：Hermes Web Dashboard 支持 drop-in UI 插件——`dashboard/manifest.json` 声明 tab/entry/css/api，后端 `plugin_api.py` 暴露 FastAPI `router`，路由自动挂载在 `/api/plugins/<name>/`。官方文档 `website/docs/user-guide/features/extending-the-dashboard.md`；`plugins/kanban` 是现成先例。**无需 fork Dashboard、无需改核心代码。**
2. **自治不是瓶颈**：插件在活跃 turn 内可通过 `ctx.subagent_lifecycle.launch(SubagentLaunchRequest(...))` 启动、等待、取消、转向子代理，支持 `goal/context/role/model/allowed_toolsets/correlation_id`；配合 cron 心跳与持久化 checkpoint，可组成"turn 预算内推进 + 跨进程续跑"的自治闭环。
3. **能力扩展不是瓶颈**：插件 `register(ctx)` 可注册工具、CLI 命令、slash 命令、hooks、skills、dashboard API；`ctx.state` 提供 durable JSON 状态、`ctx.subagent_lifecycle` 提供子代理生命周期、`ctx.llm.complete_structured` 提供结构化 LLM 评审、`ctx.get_config/set_config` 提供插件级配置。

4. **状态与技能落盘有官方 API**：`plugin_data_dir(name)` / `plugin_db(name)`（`<HERMES_HOME>/plugin-data/<name>/`，SQLite WAL）用于插件运行态；`ctx.register_skill(name, path, description, frontmatter)` 注册随插件分发的只读技能（`plugin:skill` 命名空间），用户自建技能写标准 `~/.hermes/skills/`（原生发现；插件写入需自校验/备份，`skills.write_approval` 仅门控 `skill_manage` 工具）。**不要写插件安装目录**。

5. **每轮注入经验有正式入口**：`pre_llm_call` hook 返回 `{"context": "..."}` 可把召回的经验/约束注入当轮用户消息（≤10,000 字符，超出落 `hook_outputs/`），比塞进 system prompt 更缓存友好。

6. **Dashboard 的两个运维约束**：v0.22.2 对**新增/新启用的插件**有 hot-mount fallback——首次请求 `/api/plugins/<name>/*` 时会 force_rescan 后现场挂载（`web_server_dashboard.py:899-973`）；只有"**已挂载路由的 `plugin_api.py` 代码变更**"才需要重启 `hermes dashboard`。前端资源可用 `GET /api/dashboard/plugins/rescan` 热重扫。Desktop 是另一套 SDK（`desktop/plugin.js`），与 Web Dashboard 只共享后端命名空间。

7. **自治驱动可直接复用 `/goal`**：`/goal` 是"aux 模型判 done/continue/blocked/wait + 确定性 shell 质量门 + `max_turns`"的 Ralph loop，状态存 `SessionDB.state_meta` 且可 `/resume`；插件可把 `flow status --json` 的完成判定作为 `/goal` 的 gate，获得"会话内自续跑"而无需自研 daemon。

### 3.3 本机运行时的先决条件（阻塞验收，不阻塞设计）

- **事实**：`E:\hermes\tools\python-3.14.7+20260901-win32-x64\python.exe` 当前被 ACL 拒绝（`Access is denied`，非"目录为空"）；`E:\hermes\bin\hermes.cmd` 硬编码该路径，PM venv 启动器报 `did not find executable` → 当前 `hermes` 全入口不可用。
- **反证**：`agent.log` 记录 2026-10-18 11:01 仍成功完成 `Plugin discovery complete: 56 found, 52 enabled`，并挂载 `/api/plugins/kanban/`、`/api/plugins/hermes-achievements/`；`vue3_migration` 的状态/经验库产物仍在 → **插件系统本身没坏**，唯一障碍是解释器。
- **修复**：优先 `E:\hermes\hermes-agent\setup-hermes.ps1 -RuntimeOnly`（重建 `tools\python` 与工具链）；修复后按 `hermes doctor` → `hermes plugins list` → `hermes plugins doctor` → `hermes dashboard` 自检。详见 `research/hermes-capabilities.md` 第 10 节。
- 修复前可用源码 + `pm-runtime` Python（已实测可 import `hermes_constants`）做只读验证/单测，但**插件加载/Dashboard 验收必须等运行时修复**。
- 风险等级：中（环境问题，非方案问题）。

### 3.4 结论边界（诚实声明）

- 本 PRD 的可行性判断基于 **Hermes v0.22.2 源码与官方文档**（commit `d923a5e`）；若 Hermes 升级导致插件 API 变动，需要按兼容契约回归（Hermes 承诺 manifest 向后兼容，插件 API 无全局版本号，需跟版本测试）。
- **LoopX 的真实事实（2026-10-18 核验，HEAD `105c4bc`）**：6,355★ / Apache-2.0（v0.4.8 起）/ Python CLI 壳 + TypeScript 控制面；`dependencies=[]` 但**硬性要求系统 Node ≥ 22.22.3**；主干版本 `2.0.0a1`，发布线 1.x；**CLI + JSON 是唯一稳定契约**，其 Python 内核被自身架构测试禁止外部 import；官方 DSH 插件绑定 DSH Loader/GoalBar，**Hermes 无法复用**。
- 因此 v2.2 明确采用 **方案 C（混合）**：默认自研内核（零依赖、可离线），按 LoopX 语义对齐状态机/字段；`--backend loopx` 时通过 CLI 子进程桥接（固定 argv、`--format json`、`loopx doctor` 探测、失败降级、单写者），**不 import、不双写、不复用 dsh 插件**。
- 需纠正前序 PRD/README 的两处错误认知：① 不存在 `.loopx/domain-state/<goal>/*.jsonl` 账本（真实为 `.loopx/registry.json` + `.loopx/goals/<goal>/ACTIVE_GOAL_STATE.md`，JSONL 事件溯源已被 LoopX PR #5054 退休）；② `dsh plugin add github:loopx-project/loopx` 对 Hermes 无效且 URL 用法被官方否掉。

### 3.5 与现有方案的边界（Build vs Buy）

| 方案 | 能力覆盖 | 不满足的部分 | 结论 |
|---|---|---|---|
| 社区插件 `hermes-workflows`（catalog，jacobhausler，requires ≥0.21.4） | JSON DAG、fan-out quorum、human/machine gate、fingerprint resume、Desktop DAG 视图 | 无专家注册表、无迁移领域质量信号、无经验库、英文、独立 runner 进程、gate 用 `wait.until_argv` | 可参考/共存，不替代 |
| Hermes 原生 `/goal` + kanban + cron | 单链自续跑、树状依赖、review gate、定时 | 无 DAG/评分卡/专家/经验库/可视化编排 | 作为 driver/queue 复用 |
| 修改 Hermes 核心 | 完全定制 | 违反插件契约（禁止猴补核心），升级即坏 | 否定 |
| **HERMES Flow 插件（本 PRD）** | 9 项全覆盖 | 开发量 35–50 人日（含 UI/批次/硬化）；评分模型需调优 | ✅ 推荐 |

---

## 4. 用户画像与核心场景

### 4.1 画像

| 角色 | 关注点 | 在系统中的动作 |
|---|---|---|
| **迁移负责人（架构师）** | 进度、风险、质量、成本 | 定义专家/技能、选模板、发起 Goal、看板监控、处理人工门 |
| **迁移工程师** | 具体文件怎么改、为什么失败 | 查看节点详情/证据/diff、补充技能、手动触发修复 |
| **QA / 评审人** | 评分是否可信、能否合并 | 质量报告、证据链、抽样复核、审批人工门 |

### 4.2 核心用户旅程

**S1 创建专家并绑定技能（3 分钟内）**
打开 `/flow` → 专家页 →「从提示词创建」→ 粘贴"你是代码转化专家……"→ 选择技能（Vue3 语法升级、Options API→Composition API）→ 保存 → 卡片出现在专家库，状态"空闲"，重启后仍在。

**S2 发起一次迁移**
工作台 →「新建 Goal」→ 选择项目目录 `E:\Project\xxx` → 选择模板「Vue2→Vue3 六阶段」→ 自动生成 Goal + Todo 切片 + Run → 点击「开始」→ 系统按依赖图串行推进，看板实时更新。

**S3 监控与干预**
看板显示当前节点 `transform / src/views/UserList.vue`、专家"代码转化专家"运行中、进度 42%、评分 88；某节点 429 限流 → 异常流出现"退避中 00:12"→ 自动重试成功；某节点评分 63 → 自动进入修复回环第 1/3 轮。

**S4 经验沉淀**
修复专家解决了 "antdv 1.x `a-table` scopedSlots 失效" → 自动沉淀经验卡片（坑类型/触发/解法/适用版本/命中数）→ 下一个相似文件转化前自动召回并注入提示词。

**S5 断点续跑**
用户关掉终端/机器重启/API 超时 → 重新打开 Dashboard → Run 状态"已中断，可恢复"→ 点击「继续」→ 从最后 checkpoint 续跑，不重复已完成节点。

---

## 5. 术语表（对齐 LoopX 心智模型）

| 术语 | 含义 |
|---|---|
| **Goal（目标）** | 一次迁移工程的持久目标，如"把 xxx 项目 300 文件迁移到 Vue3" |
| **Run（运行）** | Goal 的一次执行实例；同一 Goal 可多次 Run（重跑/换模板） |
| **Node（节点）** | DAG 中的最小调度单元，绑定 Agent + 技能 + 输入/输出契约 |
| **Turn（轮次）** | 一次受治理的状态转换：认领 → 执行 → 写回 → 门控；不是计时器 |
| **Turn Packet（轮次包）** | 注入子代理的最小上下文（goal/节点/切片/技能/经验/预算），防上下文膨胀 |
| **Gate（门）** | 检查点：质量门（自动评分）/ 人工门（合并、发布、删除、超预算） |
| **Evidence（证据）** | 一次 turn 的可验证产出：diff、构建日志、截图、评分、LLM 评审 |
| **Quota（配额）** | 预算/限流控制：token、调用次数、并发数、时间窗 |
| **Checkpoint（检查点）** | 可恢复状态快照（节点级 + Run 级），用于断点续跑 |
| **Receipt（回执）** | 每次状态转换的审计记录（谁、何时、做了什么、结果） |
| **Agent（专家）** | 自定义角色：名称 + 角色提示词 + 绑定技能 + 工具白名单 + 模型/预算 |
| **Skill（技能）** | 可复用的领域方法论（标准 `SKILL.md`），可绑定到多个专家 |
| **Workflow（工作流）** | 一张 DAG：节点 = Agent 任务，边 = 依赖/条件 |
| **Experience（经验）** | 从踩坑中提炼的结构化知识，可检索回灌 |
| **Lease / Heartbeat（租约/心跳）** | 节点所有权与存活证明，防并发冲突与僵尸节点 |

---

## 6. 总体架构

### 6.1 分层架构

```
┌──────────────────────────────────────────────────────────────────────┐
│ L1 交互层：Hermes Web Dashboard 插件页签 /flow（+ CLI / TUI / 通知）      │
│    工作台 · 专家 · 技能 · 编排 · 监控 · 记忆 · 质量 · 设置              │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ 同源 HTTP + WebSocket（/api/plugins/hermes_flow/*）
┌───────────────────────────────▼──────────────────────────────────────┐
│ L2 插件接口层：plugin_api.py（FastAPI router）+ register(ctx) 工具/CLI  │
└───────────────────────────────┬──────────────────────────────────────┘
┌───────────────────────────────▼──────────────────────────────────────┐
│ L3 编排层（Orchestrator）                                              │
│    Run 生命周期 · 调度器 · Turn 驱动 · 租约/心跳 · Turn 预算 · 自愈循环   │
│    **批次队列（FR-10）**：拓扑分层 · 预算装箱 · 批级门控 · 拆分/续跑      │
└───────┬───────────────────────────────────┬──────────────────────────┘
        │                                   │
┌───────▼─────────────────┐   ┌─────────────▼──────────────────────────┐
│ L4a 注册中心 Registry    │   │ L4b 门控与记忆                          │
│  Agent Registry          │   │  Quality Gate（五信号 + LLM 评审）      │
│  Skill Registry          │   │  Experience Base（FTS5 + 命中计数）     │
│  Workflow Template Lib   │   │  Preference Store（用户偏好）           │
└───────┬─────────────────┘   └─────────────┬──────────────────────────┘
        │                                   │
┌───────▼───────────────────────────────────▼──────────────────────────┐
│ L5 状态内核（State Kernel，可切换：SQLite 默认 / LoopX adapter）         │
│     Goal · Run · Node · Turn · Gate · Evidence · Quota · Checkpoint     │
│     Receipt · Experience · Lease（本地优先、跨会话持久、原子认领）        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ 复用（不重写）
┌───────────────────────────────▼──────────────────────────────────────┐
│ L6 Hermes Agent 运行时（执行层）                                        │
│  LLM/工具循环 · 技能加载 · delegate_task / subagent_lifecycle ·          │
│  cron 心跳 · browser/computer-use 验证 · memory · checkpoint · gateway  │
└──────────────────────────────────────────────────────────────────────┘
```

**三条设计原则（来自 LoopX，直接采纳）**
1. **运行时执行 turn，控制面承载工作**：HERMES Flow 不实现 LLM 循环，只治理状态与调度。
2. **一轮 turn = 一次受治理的状态转换**：用"看板 + 状态机"管理长周期工作，而不是靠一个长对话硬撑。
3. **让循环持续运转，把判断留给人**：危险/发布/合并/超预算永远人工 Gate。

### 6.2 与 Hermes 原生能力的映射（复用优先）

| 需要的能力 | Hermes 原生机制 | HERMES Flow 用法 |
|---|---|---|
| 插件装载/生命周期 | `plugin.yaml` + `register(ctx)`，`hermes plugins enable/doctor` | 标准用户插件，kind=standalone |
| 工具暴露 | `ctx.register_tool(name, toolset, schema, handler)` | 40 个（11 组）`flow_*` 工具 |
| CLI 入口 | `ctx.register_cli_command(...)` | `hermes flow <subcommand>` |
| Slash 命令 | `ctx.register_command(...)` | `/flow status`、`/flow resume` |
| 技能装载 | 标准 `SKILL.md` 发现 + `ctx.register_skill(name, path, description, frontmatter)` | 内置技能包 + 用户技能双向加载 |
| Dashboard UI | `dashboard/manifest.json`（tab/entry/css/api）+ `plugin_api.py` | `/flow` 页签 + `/api/plugins/hermes_flow/*` |
| 子代理执行 | `ctx.subagent_lifecycle.launch/wait/status/cancel/steer` | 每个 Node 一次受控子代理执行 |
| 兼容式委派 | `delegate_task` 工具 | 无 lifecycle 权限时的降级路径（Turn Packet 文本） |
| 结构化 LLM 评审 | `ctx.llm.complete_structured(...)` | 质量门的"行为一致性/代码审查"信号 |
| 每轮经验注入 | `pre_llm_call` hook（返回 `{"context": ...}`，≤10k 字符） | 经验召回 / 用户偏好 / 当前节点约束 |
| 收尾验证门 | `pre_verify` hook + `hermes verify` | 无验证证据不允许结束；构建/测试 recipe |
| 自续跑驱动 | `/goal`（Ralph loop + 确定性 gate + `max_turns`） | 无人值守推进的 driver 之一 |
| 定时心跳 | Hermes cron（或插件 CLI + 系统计划任务） | 无人值守推进 / 卡死检测 |
| 运行态存储 | `ctx.state`（插件级 durable JSON）+ `plugin_db()`（WAL SQLite） | 注册表/配置/运行态，**不写安装目录** |
| 插件配置 | `ctx.get_config/set_config` | 阈值、并发、模型、内核选择 |
| 事件钩子 | `ctx.register_hook(...)`（`pre_tool_call`/`post_tool_call`/`subagent_stop`/`on_session_end` 等） | 工具结果记账、异常捕获、子代理结束回收 |
| 浏览器验证 | Hermes browser 工具 / `plugins/browser` | 质量门浏览器信号 + 截图证据 |
| 原生记忆 | memories/、MEMORY.md、会话搜索、memory provider | 偏好/工程结论写入原生记忆；经验库独立结构化 |
| 回滚 | checkpoints-and-rollback | 节点级代码回滚兜底 |
| 消息注入 | `ctx.inject_message(...)` | 卡住时向父会话注入状态提醒/下一步指令 |

> 具体方法签名与源码位置见 `research/hermes-capabilities.md` 第 2 节（逐项 file:line）。

### 6.3 部署形态

- **形态 A（主形态）**：Hermes 用户插件 —— `E:\hermes\plugins\hermes_flow\`，随 Hermes 启动加载，Dashboard `/flow` 页签使用。
- **形态 B（可选，后续）**：独立 CLI / 无头守护（`hermes flow daemon`），通过 TUI Gateway JSON-RPC 或 OpenAI 兼容 API 驱动，不依赖 Dashboard 打开。
- **形态 C（可选，后续）**：把内核导出为 Python 包（`pip install hermes-flow-core`），供其他 harness 复用（LoopX 风格）。

---

## 7. 功能需求

> 优先级：P0 = MVP 必须；P1 = 首个可用版本；P2 = 增强。
> 每条包含：描述 / 交互要点 / 业务规则 / 异常与边界 / 验收标准。

### FR-1 专家（Agent）注册与技能绑定（P0）

**描述**：用户通过"角色提示词"创建专家，专家可绑定 0..N 个技能，可配置模型/工具白名单/预算；插件启动时自动加载全部专家与绑定关系。

**交互要点**
- 专家页：卡片/表格双视图；卡片显示名称、角色摘要、绑定技能 chips、状态、最近运行、成功率。
- 「从提示词创建」三步向导：①粘贴提示词（自动识别角色名/职责/输入输出，可编辑）→ ②选择技能（多选，可内联新建）→ ③高级配置（模型、工具集、最大轮次、超时、温度）→ 保存。
- 支持导入/导出 JSON、复制模板、克隆专家、停用/启用。
- 专家详情抽屉：提示词全文（可编辑）、技能绑定管理、最近 20 次运行记录、平均评分。

**业务规则**
- `name` 唯一；提示词必填且 ≥20 字符；技能引用必须存在，否则保存失败并高亮。
- 删除被工作流引用的专家需二次确认，并提示受影响的工作流。
- 技能解绑不影响已生成的历史 Run 证据。
- 自动加载：插件 `register()` 时从 `plugin_data_dir("hermes_flow")/agents/*.json` + 内置 `agents/*.yaml` 合并加载；冲突时用户目录优先。
- **技能如何真正进入子代理**：Hermes `delegate_task` 没有 skills 参数，`ctx.subagent_lifecycle` 也只接受 goal/context/model/toolsets。因此插件必须在 Turn Packet 中注入"技能摘要 + `skill_view("<plugin>:<skill>")` 指令"，或让子代理自行调用 `skill_view`；不得假设存在"专家→技能"的原生绑定。

**异常与边界**
- 提示词过长（>32k）：拒绝并提示拆分或改用技能。
- 技能文件缺失/损坏：专家降级为"无技能"并在 UI 标黄，不阻塞其他专家加载。
- 并发编辑：基于 `updated_at` 的乐观锁，冲突时提示刷新。

**验收**
- 3 步创建成功；重启 Hermes 后专家与绑定关系完整恢复；被引用技能不可静默删除；导出文件可被另一台机器导入。

### FR-2 技能（Skill）注册与展示（P0）

**描述**：技能以标准 `SKILL.md` 为唯一事实源，插件提供技能库展示、创建/导入、校验、绑定统计与使用效果。

**交互要点**
- 技能库：列表展示名称、描述、适用阶段、绑定专家数、最近使用、平均提效（可选）；支持按阶段/标签筛选与搜索。
- 「新建技能」：表单（名称、描述、适用阶段、Procedure/Pitfalls/Verification 三段式）→ 实时校验 frontmatter → 保存为 `SKILL.md`。
- 「导入技能」：上传 `.md`/目录/粘贴；自动校验 authoring 规范（描述长度、section 顺序、工具名反引号等）。
- 技能详情：正文预览（Markdown 渲染）、绑定专家、命中记录、编辑历史。

**业务规则**
- 技能目录：用户技能 `$HERMES_HOME/skills/<name>/SKILL.md`；插件内置技能 `plugins/hermes_flow/skills/<name>/SKILL.md`。
- 自动加载：启动时扫描并注册；`ctx.register_skill` 用于内置技能命名空间，用户技能走 Hermes 原生发现。
- 校验失败不写入，返回逐条错误；覆盖同名技能需显式确认。

**异常与边界**
- 技能名冲突：内置 vs 用户同名 → 用户技能优先，UI 标注"覆盖内置"。
- 非法 frontmatter/编码问题：拒绝并保留草稿。

**验收**
- 新建技能后该技能可被专家绑定，并在下次运行中实际注入；校验规则与 Hermes skill authoring 标准一致。

### FR-3 工作流编排（P0）

**描述**：可视化 DAG 编排"先 A 后 B、条件分支、循环修复、质量门、人工门"，并沉淀为可复用模板。

**节点类型**
| 类型 | 语义 | 关键配置 |
|---|---|---|
| `agent_task` | 调度一个专家完成一个切片任务 | agent、skills、input、output、timeout、max_attempts |
| `batch` | 对一组文件/目录批次串行（可选同层并行）执行 | **唯一 schema（§8.4/附录 G）**：`source/order/size/adaptive/context_budget_chars/inner_loop/concurrency/max_split_depth/split_on_failure/quality_gate_per_batch/write_mode`；旧 `glob/batch_size/parallel` 为 deprecated alias |
| `quality_gate` | 自动评分与门判定 | signals、weights、pass/warn/rework 阈值 |
| `human_gate` | 人工审批 | 问题描述、选项（通过/驳回/暂停）、超时策略 |
| `condition` | 条件分支 | 表达式（评分/数量/状态） |
| `loop` | 回环（修复/重跑） | 循环体、退出条件、最大轮数 |
| `join` | 汇聚并行分支 | 策略（all/any/n-of-m） |
| `script` | 确定性脚本/命令（构建、类型检查） | command、cwd、timeout、允许失败 |

**交互要点**
- 左侧节点库、中间画布（缩放/拖拽/框选/连线/自动布局）、右侧属性面板。
- 节点卡片显示：类型图标、名称、绑定专家/技能、耗时/评分（运行态）、状态色。
- 顶部：保存/发布/试运行/校验；版本号与变更记录。
- 模板库：内置「Vue2→Vue3 六阶段」（见附录 A）、「单文件试点」、「质量返工闭环」。
- 校验：环检测、悬空边、无入口、孤立节点、未绑定专家的 agent_task、缺失质量门。

**业务规则**
- 工作流保存为 JSON DSL（schema 版本化），支持导入/导出。
- 发布后生成不可变版本；Run 固定引用某个版本，避免"改流程影响在跑的 Run"。
- 节点可配置 `parallel: true`；否则受串行硬约束保护。

**异常与边界**
- 非法 DAG：保存/发布即拒绝，错误定位到节点/边。
- 模板实例化：自动映射变量（项目路径、包管理器、阈值），缺失变量要求补齐。

**验收**
- 能拖拽搭出六阶段模板并通过校验；非法图被拒绝且错误可定位；导出 JSON 可在另一环境导入。

### FR-4 运行监控（P0）

**描述**：实时展示 Run 的步骤、专家状态、进度、评分、异常与证据，支持历史回放。

**交互要点**
- 顶部 Goal 卡：名称、状态、进度环、预计剩余、开始时间、当前节点。
- 流程视图：DAG 节点着色（灰=未开始、蓝=运行中、绿=通过、黄=警告/回环、红=失败、橙=等待人工）。
- 专家状态面板：每个专家的状态、当前任务、已处理/总数、平均评分、最近一次耗时。
- 时间轴/日志流：turn 级事件（claim/execute/gate/retry/complete），支持过滤与搜索。
- 证据抽屉：diff（语法高亮）、构建日志、浏览器截图、评分明细、LLM 评审意见。
- 历史回放：选择某次 Run → 按时间轴回放（可倍速），查看每步决策。

**实时性**
- Dashboard 通过 **WebSocket** 订阅 `/api/plugins/hermes_flow/ws?run_id=...&ticket=...`，事件 ≤1s 内到达；断线自动重连并按 `last_event_seq` 续传已落库事件。
- 采用 WebSocket 而非浏览器原生 `EventSource`：Dashboard 的 `/api/*` 要求 `X-Hermes-Session-Token`/Bearer，而 `EventSource` 不能带自定义头；kanban 插件已用 `?token=` + WebSocket 的先例（`plugins/kanban/dashboard/plugin_api.py`）。备选：`fetch` + `ReadableStream` 手动实现 SSE 并带 token。

**业务规则**
- 状态以服务端为准，UI 只读投影；所有写操作走 action API 并返回新状态。
- 证据不可变（追加式），修复轮次保留每轮证据。

**验收**
- 两个浏览器同时打开看到一致状态；断网 30s 重连后补齐事件；历史回放与真实事件序列一致。

### FR-5 记忆系统（P1，经验库为 P0）

**描述**：四层记忆——turn 切片上下文、Run/工程状态、长期经验库、用户偏好；经验可沉淀、检索、回灌，并可晋升为技能。

**交互要点**
- 记忆中心三个 tab：经验库 / 用户偏好 / 工作区记忆。
- 经验卡片：坑类型、触发条件、解法、适用版本/技术栈、命中次数、来源 Run/节点、置信度；支持搜索/筛选/编辑/归档。
- 「沉淀」：修复成功或人工标注后自动生成草稿，人工确认入库（防噪音）。
- 「回灌」：节点执行前自动检索 Top-K 经验注入 Turn Packet；UI 显示"本轮注入了 3 条经验"。
- 「晋升技能」：一条经验被复用 ≥N 次 → 提示生成技能草稿。

**业务规则**
- 去重键：`category + trigger_normalized + stack`；重复命中 `hit_count++` 并更新 `last_seen`。
- 检索：阶段 + 关键词（FTS5）+ 可选向量相似度；按命中数与新鲜度加权。
- 偏好：命名风格、注释语言、阈值、审批粒度、模型偏好；写入插件配置并同步 Hermes 原生记忆。
- 隐私：仅本地存储；支持按 Goal 清理；导出为 JSON。

**异常与边界**
- 经验库损坏：降级为"暂无经验"并告警，不阻塞运行。
- 低质量经验：需人工确认才入库；自动沉淀默认 `draft` 状态。

**验收**
- 同一坑位第二次出现时可被检索到并注入；经验去重正确；清理/导出可用。

### FR-6 异常处理与自治循环（P0）

**描述**：任务执行期间的限流、截断、超时、进程中断、依赖缺失、构建失败、质量低分、专家跑偏等异常，系统自动识别→分类→恢复→续跑，直到完成或触发人工门。

**异常分类与策略（9 类）**
| 异常 | 检测 | 自动处理 | 上限/升级 |
|---|---|---|---|
| `rate_limit`(429) | 错误码/响应头 | 指数退避 + jitter（1s→2s→…→5min），保留配额 | 连续 8 次或 >30min → 人工 |
| `truncated` | finish_reason=length / 输出截断 | 落 checkpoint，缩小切片（按 AST/组件边界）续跑 | 同节点 3 次 → 拆分任务 |
| `timeout` | 超时阈值 | 重试（可使用降级模型/更小上下文） | 3 次 → 人工 |
| `process_interrupt` | 启动时发现 running 节点租约过期 | 从最近 checkpoint 恢复，节点幂等重放 | 无限（设计内） |
| `dependency_missing` | 构建/import 报错 | 回退到 deps 阶段重新分析并修复依赖 | 2 次 → 人工 |
| `build_failed` | 构建门失败 | 进入 fix 回环（修复专家） | 3 轮 → 人工 |
| `low_score` | 质量门 <阈值 | 进入 fix 回环，注入低分证据与经验 | 3 轮 → 人工 |
| `agent_drift` | 输出不符合契约/越权工具/跑偏 | 取消子代理，回收租约，重派更小切片 | 2 次 → 人工 |
| `quota_exhausted` | 预算/配额耗尽 | 暂停 Run，等待窗口/人工扩容 | 人工 |

**复用 Hermes 原生恢复能力（不要重造）**
- 异常分类参考 `agent/error_classifier.py` 的 **29 种 `FailoverReason`**（rate_limit/server_error/timeout/auth/billing/context_overflow/…，覆盖 30+ 语义类别）与"每种错误带恢复建议"的模式；插件维护自己的 `kind` 映射表，不复制其实现。
- 退避直接复用语义：`retry_utils.py` 的 `Retry-After` 解析、`jittered_backoff`（base 5s / max 120s / jitter 0.5）、`adaptive_rate_limit_backoff`。
- 模型 fallback 链由 Hermes 处理（429/5xx/401/403 依序 fallback）；插件只负责"节点级重试预算"与"是否换专家/拆切片"。
- 文件级回滚可用 Hermes checkpoint（`~/.hermes/checkpoints/store/`，默认关闭，需开启）；插件节点级 checkpoint 记录**逻辑状态**（节点/attempt/证据引用），两者互补。
- 会话恢复：`--resume`/`/resume` 恢复对话；工作流恢复由插件 `flow resume` 负责，二者独立。

**自愈循环**
```
while goal.status != done:
  node = schedule_next()                     # 依赖满足 + 租约可用 + 未超预算
  if none: if waiting_gate -> notify; else break
  lease = claim(node, ttl=10min)
  packet = build_turn_packet(node, recall_experience)
  try:
    result = run_turn(packet)                # 子代理 / 委派
    evidence = collect(result)               # diff/日志/截图
    score = quality_gate(node, evidence)
    if score >= pass: complete(node); spend(quota)
    elif score >= warn: complete(node, warn=True); record_todo
    else: rework(node, evidence, score)      # 回环
  except Exception as e:
    kind = classify(e)
    policy = recovery_policy(kind, node)
    checkpoint(node); backoff(policy); retry_or_escalate(node, kind)
  finally: release(lease)
```
- **Turn 预算**：每次 driver 运行最多处理 N 个节点或 T 分钟，然后干净退出并落 checkpoint（避免上游超时/截断导致整段丢失）。
- **心跳与僵尸回收**：租约 TTL + 心跳；进程重启后过期租约节点自动回收重排。
- **幂等**：节点执行前写 `attempt_id`；写回带 `expected_version`（乐观锁），重复写回被拒绝。
- **人工门**：超限/危险动作/超预算 → 创建 `human_gate`，Dashboard 通知，支持通过/驳回/暂停/改参数。

**验收**
- 注入 429：自动退避重试成功；注入截断：checkpoint 后从断点续跑；杀进程重启：恢复且不重复已完成节点；连续 2 小时无人值守不中断。

### FR-7 质量门控（P0）

**描述**：每个关键节点出产出后自动评分并判定是否放行；低分自动回环修复，超限升级人工。

**五信号评分（0–100 加权，可按项目配置）**
| 信号 | 默认权重 | 实现 |
|---|---|---|
| AST/语法正确 | 20 | Vue SFC 解析 + JS/TS 解析（Node 子进程：`@vue/compiler-sfc`/Babel） |
| 构建通过 | 25 | `vite build`（或增量构建）成功/失败 + 错误数 |
| 类型检查 | 15 | `vue-tsc --noEmit` 错误数 |
| 浏览器验证 | 25 | 路由渲染 + 关键交互（Playwright/CDP）+ 控制台错误 + 截图 |
| 行为一致性 | 15 | 结构化 LLM 评审（对照原组件语义/交互清单）+ 可选快照 diff |

- **门控规则**：≥85 通过；70–84 通过但记警告与待办；<70 回环；回环最多 3 轮，仍不达标 → 人工门。
- **硬门**：构建失败或浏览器白屏直接不通过（不做加权稀释）。
- **证据链**：每次评分保存证据（命令、退出码、日志摘要、截图、LLM rubric 结果、模型与 prompt 版本）。
- **防误判**：LLM 评审需给出结构化理由与置信度；低于置信度阈值时降级为"需人工复核"，不自动放行。
- **工具链探测**：`@vue/compiler-sfc`/`vue-tsc`/`vite` 优先使用目标项目 `node_modules`；不可用时回退 Hermes 自带 Node（`tools\node-*`，需显式注入 PATH）；仍不可用则该信号记 0 并在证据中标注 `toolchain_unavailable`（不静默通过）。
- **抽样复核**：按 N% 抽样人工复核，记录误判率，用于调权重。

**复用 Hermes 原生验证原语**
- `pre_verify` hook：agent 准备收尾且本轮编辑过代码时触发，可 continue/block-stop → 强制"先有验证证据再收尾"。
- `hermes verify`：探测项目 recipe（bootstrap→build→test→start→readiness→teardown），`--json` 输出可作为构建/测试信号的数据源。
- `/goal` 的确定性 shell 门：`exit 0` 才允许 judge 判 done；可作为"整条 Run 完成"的最终门。
- browser 工具（browser_navigate/exec/CDP）与 computer_use：浏览器信号与截图证据。
- `ctx.llm.complete_structured`：行为一致性/代码审查信号，带 JSON schema 校验。

**交互要点**
- 质量报告页：评分分布（直方图）、按阶段/专家/文件下钻、低分 Top 列表、回环记录、误判标记。
- 节点详情：五信号条形/雷达、证据列表、门槛值与判定、重新审查按钮。
- 设置页可调权重与阈值（需权限），变更记录审计。

**验收**
- 对样例项目评分与预期一致；低分触发回环；硬门失败不被加权稀释；报告可下钻到证据。

### FR-8 LoopX 借鉴与集成（P1）

**描述**：采用 LoopX 的"控制面/运行时分离 + turn 受治理转换 + quota/receipt"治理模型；默认自研轻量内核，可选切换到 LoopX 后端（CLI 桥接）。

**LoopX 真实事实（核验于 2026-10-18，HEAD `105c4bc`）**：6,355★ / Apache-2.0（v0.4.8 起）/ Python CLI 壳 + TypeScript 控制面；`dependencies=[]` 但硬性要求系统 **Node ≥ 22.22.3**；主干 `2.0.0a1`，发布线 1.x；**CLI + JSON 是唯一稳定契约**；Python 内核被其架构测试禁止外部 import；官方 DSH 插件不能用于 Hermes。详见 `research/loopx-analysis.md`。

**实现规则**
- **语义对齐（默认内核）**：Goal/Todo/Turn/Gate/Evidence/Quota/Checkpoint/Receipt 的字段与状态机按 LoopX 语义设计；注意 LoopX 官方模型是"六层存储 + 四种职责 + Turn 契约"，"五原语"只是前序对 5 个 CLI 动作的归纳，文档中不宣称其为 LoopX 术语。
- **可切换内核**：`FlowKernel` 协议（`should_run / claim / update / refresh_state / spend_slot`）；`SQLiteKernel` 默认；`LoopXKernel` **仅通过 CLI 子进程**调用（固定 argv、`--format json`、超时、禁 shell、stderr 只进日志、非零退出映射结构化错误）。**checkpoint/restore 属于编排层能力，不放进内核协议**——两内核共用同一套本地 JSON checkpoint（LoopX 后端只提供状态投影；其 "checkpoint" 是 boundary authority/vision checkpoint，不是可恢复的任意快照）。
- **启动探测**：`loopx --version` / `loopx doctor` + `node --version`；不可用 → 工具返回 `unavailable` 并自动降级 SQLite，**绝不假装成功**。
- **单写者纪律**：一个 Goal 同时只允许一个后端写；切换流程 = `export → 人工确认 → 切换 → 只读校验`，禁止双写；Run 记录 `kernel` 字段，切换只对新建 Run 生效。
- **版本策略**：pin 到与官方 dsh 插件同款的下限并冻结小版本：`loopx>=1.2.4,<1.3`（或精确 `1.2.4`），CI 固定版本跑契约测试；JSON 解析未知字段 additive。
- **Node 依赖治理**：LoopX 控制面要求 Node ≥22.22.3；启动探测 `node --version`，必要时把 Hermes 自带 node 目录注入子进程 `PATH`（`E:\hermes\tools\node-26.7.0-win32-x64` 不保证在 PATH）；不可用时工具返回 `unavailable` 并降级。
- **合规**：不 fork、不复制内核代码，仅 CLI 调用；保留 NOTICE 与链接，文档注明"非官方集成"。

**验收**
- 同一操作序列在两种内核下 `should_run` 布尔、`next_todo` 选择、gate 阻塞、spend 幂等一致（差异清单入 repo）；
- 切换后旧 Run 仍可查看与恢复；LoopX/缺少 Node 时自动降级且 UI 明示；
- 不出现双写（同一 goal 两个后端同时写）导致的记录分叉。

### FR-9 设置与运维（P1）

- 内核选择、模型/委派配置、并发与配额、门控阈值与权重、证据保留策略、通知（Dashboard/系统通知）、诊断（插件 doctor、运行时自检）、数据导出/清理。
- 插件安装/升级/卸载：标准 `hermes plugins enable/disable/remove`；升级不丢 `$HERMES_HOME/flow/` 数据；提供 `schema_version` 迁移。

---

### FR-10 批量循环与批次调度（P0，v2.2 新增）

**描述**：当项目文件量大时，系统把待转化文件按依赖与上下文预算拆成多个**批次（Batch）**；每个批次是一个独立子任务，由绑定的专家子代理**循环处理批内文件**；插件负责批次队列的循环调度、失败隔离、质量门控与断点续跑。

**三层循环模型**

| 层 | 谁在循环 | 循环对象 | 默认策略 |
|---|---|---|---|
| L1 外层（插件调度器） | 控制面 | 批次队列 | 波次串行（第 N 批完成才启动 N+1） |
| L2 中层（可选） | 控制面 | 同一依赖层（wave）内的批次 | 默认 1；可配 2–3，仅同 wave 并行 |
| L3 内层（子代理） | 子代理自身 | 批内文件（按拓扑序） | `inner_loop=serial`，一次 launch 处理整批 |

**专家循环配置（Agent.loop_policy）**
```json
{
  "enabled": true,
  "mode": "per_batch",
  "inner_loop": "serial",
  "max_files_per_batch": 7,
  "max_batches_per_launch": 1,
  "max_concurrent_batches": 1,
  "context_budget_chars": 28000,
  "split_on_failure": true,
  "max_split_depth": 2,
  "checkpoint_each_batch": true,
  "quality_gate_per_batch": true,
  "write_mode": "staging_apply"
}
```
- `mode`：P0 支持 `per_batch`（每批一次子代理）/ `single_file`（一批一文件，最稳）；`persistent_child`（一个子代理循环多批）为 **P2 实验**，默认关闭，需 child 内每批 checkpoint 与 B15 验收。
- `max_batches_per_launch`：**P0 固定为 1**（每批一个子任务、一个子代理）；>1 仅 P2 实验。
- `max_concurrent_batches`：仅在批次处于**同一依赖 wave** 时生效；跨 wave 强制串行；并行批必须使用独立 worktree/staging。
- `write_mode`：默认 `staging_apply`——子代理只写 staging，插件校验后备份并原子应用（防止越界写与写后崩溃重复转换）。
- 专家卡与详情抽屉展示循环配置与当前批次进度（`批次 18/43 · 文件 126/287`）。

**批次规划（Batch Planning）**
1. 依据依赖图做拓扑排序（复用前序 `topo_order_files`），计算每个文件的依赖层级 `level`。
2. 按 `level` 分 wave；同 wave 内文件互不依赖。
3. 每个 wave 内按拓扑序做"预算装箱"：累计估算字符数 ≤ `context_budget_chars`、文件数 ≤ `max_files_per_batch`；超大文件单独成批。
4. 高风险文件（router/entry）单独成批并标记 `priority=high`，**提前人工复核但不改变 wave 顺序**；store 等被依赖文件必须在前序 wave。
5. 分批结果持久化，支持导出/复现；跨批依赖由"前序批 completion + 依赖摘要"保证。

**调度语义**
- 批次状态：`planned → ready → running → gated → done`；失败分支：`retry / split / repair / manual`。
- **原子认领**：`claim(batch)` 写租约（owner + TTL + heartbeat），同一批同一时刻只允许一个子代理。
- **driver 单例**：Run 级租约锁，同一 Run 同一时刻只有一个 driver（cron/`/goal`/会话）可推进；独立 heartbeat（30s）续租。
- **执行通道**：
  - 首选 `ctx.subagent_lifecycle.launch(...)`（可指定 model/toolsets/correlation_id/working_directory；进程内并发池 8）；**lifecycle 无 `output_schema`**，逐文件 JSON 由"提示词约束 + 插件校验 + 一次格式纠正重派"保证。
  - 可选 `delegate_task(tasks=[≤并发上限])` 波次批量（主 Agent 在环时；>上限会报错，插件必须切波）；该通道原生支持 per-task `output_schema`，但 **summary 上限 24,000 字符**（lifecycle 为 32,000）。
  - 不推荐持久循环子代理；kanban dispatcher 作为 P2 规模化后端。
- **wait 分片**：单次 `wait()` ≤60s，避免阻塞心跳/取消；跨 tick 保留 handle（进程内 1 小时），丢失则按租约过期 + `applied_hash` 对账续跑。
- **Turn 预算**：`tick_budget_seconds=600` 与 `max_batches_per_tick=10` 双约束；到点落 checkpoint / 保留 handle 后干净退出。
- **批内循环**：子代理按 `order` 顺序处理文件，逐文件返回 JSON 结果（`files[{path,status,changes,notes,error}]`）；**只写 `staging_dir`**，不得直接写工作区。
- **写入治理（staging-only + 工作区审计）**：
  1. **Packet 提供绝对路径**：`project_root`（只读源）、`staging_root`（可写）、每个文件的 `source_path` 与 `staging_path`；`working_directory=project_root`，提示词明确"读取 source_path，写入 staging_path，禁止修改工作区"。
  2. **启动前基线**：记录 `git status --porcelain` + `git diff --name-only`（或全量 hash 快照）到 `batches.workspace_baseline_json`。
  3. **结束后审计**：再次采集工作区变更，`post - pre - 批内文件集合` 非空 → 判定越界写；用备份/`git checkout --` 回滚越界文件，标记 `agent_drift` + `FLOW_BATCH_WRITE_SCOPE` + 人工门（B11）。
  4. **应用**：审计通过后，校验 staging 文件集合 ⊆ 批内文件 → 备份 → 原子替换 → 记录 `applied_hash`。

**失败与恢复（批次/文件级）**
| 异常 | 处理 |
|---|---|
| 429 限流 | 暂停当前 wave → 退避 → 重新 launch 该批 |
| 输出截断/上下文超限 | 批次二分拆分（`split_depth+1`，最多 2 层），仍失败转 `single_file` |
| 子代理超时/停滞 | `wait` 分片超限 → `cancel()` → 重试（可降级模型）→ 拆批 |
| 子代理崩溃/进程退出 | 租约过期 → 批次回 `ready`；按 `applied_hash/staged_path` 对账，只重跑未应用文件 |
| handle 丢失（跨进程/超 1h） | 租约过期 → `ready` → 对账 → 重派未应用文件 |
| 结果 JSON 解析失败 | 一次格式纠正重派；仍失败 → `single_file` 或人工门 |
| **越界写** | staging 文件集合 ⊄ 批内文件、或工作区审计发现批外变更 → 回滚 + 拒绝 apply + `agent_drift` + 人工门 |
| 部分文件失败 | 生成 repair 子批（只含失败文件），最多 3 轮 |
| 质量低分 | 批次级修复回环；超限 → 人工门 |
| 文件被外部修改 | 标 `manual/stale`，不覆盖，转人工 |

**幂等与不重复（staging-apply）**：`batch_items` 以 `(group_id,file_path)` 唯一；写前记 `attempt_id + base_hash`；写后记录 `applied_hash`；恢复时对账——一致则跳过、staging 未应用则重新校验应用、不一致转 `manual`；批次 `done` 前校验所有文件 `applied|manual`。

**质量门控（三层）**：**批级**只做 AST/parse + diff/staging 白名单（硬门）+ 可选 scoped 单测/LLM 评审；**wave 级**可选增量构建/路由 smoke；**聚合级**才执行全量 build/type/browser 硬门 + 覆盖率（100%）+ 加权评分。批级通过 ≠ 项目通过；全量硬门只做一次，避免部分迁移状态下"第一批永远无法通过"。

**UI 要求**：工作台批次进度条；监控页批次队列（按 wave 分组）+ 批内文件状态；编排页 batch 节点 `×N 批` 与属性面板；专家详情循环配置；质量页按批次下钻；设置页批量参数。

**验收（B1–B17）**
- [ ] B1 1000 文件合成项目生成可复现批次计划，无跨依赖倒置；
- [ ] B2 287 文件样例全批完成、文件覆盖率 100%、聚合门通过；
- [ ] B3 批内部分失败只 repair 失败文件，成功文件不重复处理；
- [ ] B4 截断自动拆批成功；B5 429 波次暂停/恢复无重复写；
- [ ] B6 批次运行中杀进程，重启后只重跑未完成文件；
- [ ] B7 低分批次 repair 后评分提升，3 轮后人工门；
- [ ] B8 同层并行仅限同 wave（独立 worktree），结果顺序稳定；
- [ ] B9 每个子代理 context ≤32,000 字符、结果 ≤24,000（delegate 通道）；
- [ ] B10 批次 UI 与内核状态一致，断线重连补齐事件；
- [ ] B11 越界写被拒绝并回滚；B12 写后崩溃不重复转换/应用；
- [ ] B13 lifecycle 结果校验 + 一次格式纠正重派；B14 driver 单例（双 cron 不重复推进）；
- [ ] B15 persistent_child（P2 可选）每批 checkpoint 可恢复；B16 部分迁移下批级门可通过、全量门只在聚合失败；
- [ ] B17 100 批连续运行（注入 10 次故障）无人介入完成率 ≥95%，且不超 Run 总预算。

> 详细调研、方案对比、算法伪代码与证据索引见 `research/batch-loop-analysis.md`；数据模型见 §14.6，DSL 见附录 G。

## 8. 工作流引擎设计

### 8.1 DSL（版本化 JSON）

```json
{
  "schema": "hermes-flow/workflow@1",
  "id": "vue3-migrate-6phase",
  "name": "Vue2→Vue3 六阶段迁移",
  "version": "1.2.0",
  "vars": { "project_root": "", "package_manager": "pnpm", "pass_score": 85 },
  "nodes": [
    {"id":"analyze","type":"agent_task","name":"结构分析","agent":"结构分析专家",
     "skills":["vue3-analyze"],"input":{"project_root":"${project_root}"},
     "output":{"file":"reports/analyze.json"},"timeout_s":1800,"max_attempts":2},
    {"id":"deps","type":"agent_task","name":"依赖分析","agent":"依赖分析专家",
     "skills":["vue3-deps"],"depends_on":["analyze"]},
    {"id":"transform","type":"batch","name":"代码转化","agent":"代码转化专家",
     "skills":["vue3-transform"],"depends_on":["deps"],
     "batch":{"source":"report:deps.files","order":"topo","size":7,"adaptive":true,
              "context_budget_chars":28000,"inner_loop":"serial","concurrency":1,
              "max_split_depth":2,"split_on_failure":true,
              "quality_gate_per_batch":true,"write_mode":"staging_apply"}},
    {"id":"quality","type":"quality_gate","name":"质量评分","depends_on":["transform"],
     "gate":{"signals":["ast","build","types","browser","behavior"],
             "weights":[20,25,15,25,15],"pass":85,"warn":70,"max_rework":3}},
    {"id":"fix","type":"loop","name":"修复回环","depends_on":["quality"],
     "when":"${quality.verdict} == 'rework'","agent":"修复专家",
     "skills":["vue3-fix"],"exit":"${quality.verdict} == 'pass'","max_rounds":3},
    {"id":"verify","type":"agent_task","name":"浏览器验证","agent":"浏览器验证专家",
     "skills":["vue3-verify"],"depends_on":["quality"],"parallel":true},
    {"id":"review","type":"human_gate","name":"人工验收","depends_on":["verify","fix"],
     "question":"是否合并迁移分支？","options":["approve","reject"]}
  ],
  "edges": [
    {"from":"analyze","to":"deps"},
    {"from":"deps","to":"transform"},
    {"from":"transform","to":"quality"},
    {"from":"quality","to":"fix","condition":"rework"},
    {"from":"quality","to":"verify","condition":"pass"},
    {"from":"verify","to":"review"},
    {"from":"fix","to":"review"}
  ]
}
```

### 8.2 执行语义

1. **就绪判定**：入边全部满足（含条件边）+ 未被租约占用 + 未超预算 + 未在人工门后。
2. **串行硬约束**：非 `parallel` 节点同一时刻只允许一个 running；调度器拒绝第二次 claim（不是靠提示词）。
3. **切片上下文**：每个 `batch` 子任务只注入当前文件/组件切片 + 相关依赖 + 经验，不注入全量历史。
4. **写回幂等**：`complete(node, attempt_id, expected_version)`；重复/过期写回拒绝并记录冲突。
5. **条件/循环**：条件表达式只读白名单变量（评分、状态、计数），避免任意代码执行；实现可选 **CEL（Common Expression Language）** 或自有白名单 DSL（M2 决策并锁定），循环上限强制。
6. **人工门**：进入 `waiting_gate`，Run 暂停但不释放状态；通知 + 审批 API；超时策略可配。
7. **终止**：所有终态节点完成且无待办 → Run `succeeded`；任一不可恢复失败 → `failed`；预算耗尽 → `paused`。

### 8.3 状态机

```
pending → ready → claimed → running → gated(pass|warn) → done
                    │            │
                    │            ├─ rework → fix → running(再次)
                    │            └─ failed → retry(≤N) / manual_gate
                    └─ lease_expired → ready（幂等重放）
```

Run：`draft → running ⇄ paused → succeeded | failed | cancelled`；`waiting_gate` 是 `paused` 的子状态（有未决人工门）。

---

### 8.4 批次规划与调度（FR-10 的引擎实现）

**节点扩展**：`batch` 节点新增配置块：
```json
{"type":"batch","batch":{
  "source":"report:deps.files", "order":"topo", "size":7, "adaptive":true,
  "context_budget_chars":28000, "inner_loop":"serial", "concurrency":1,
  "max_split_depth":2, "split_on_failure":true,
  "quality_gate_per_batch":true, "write_mode":"staging_apply"
}}
```

**规划算法（拓扑分层 + 预算装箱）**
```
topo = topo_sort(files)                       # 复用前序 core migrator.topo_order_files
level[v] = 1 + max(level[d] for d in deps[v])
for wave in group_by(level):
  pending = wave (topo order)
  while pending:
    batch, budget = [], context_budget_chars - prompt_overhead
    while pending and len(batch) < max_files_per_batch:
      f = pending[0]
      if estimate_chars(f) > budget and batch: break
      batch.append(f); pending.pop(0); budget -= estimate_chars(f)
    if not batch: batch = [pending.pop(0)]     # 超大文件单独成批
    emit Batch(wave, files=batch)
```
- `estimate_chars(f) = file_size * 1.2 + 2000`；可用真实 token 估算器替换。
- 自适应：截断则二分拆批（≤2 层）；连续 3 批成功可放大批（上限 12）；429 时并发 -1，成功时 +1（上限 3）。

**批次状态机**
```
planned → ready → running → gated ─pass→ done
                    │          ├warn→ done(记录待办)
                    │          └rework→ repair(failed files)→ gated
                    ├failed→ retry(≤3) / split(≤2) / manual
                    └lease_expired→ ready(按 hash 幂等重放)
BatchGroup: planning → running ⇄ paused → aggregating → succeeded|failed|manual
```

**线程模型与写入治理**：调度器单线程（tick 驱动）+ **Run 级 driver 单例锁**（防多 cron/会话重复推进）→ 认领批次 → 通过 `lifecycle.launch` 提交到进程内 8 线程池；插件以 ≤60s 的 `wait` 分片轮询（不阻塞心跳/取消），跨 tick 保留 handle（进程内 1h），丢失则租约过期 + `applied_hash` 对账。子代理只写 `staging/<run>/<batch>/`，插件校验 staging 文件集合 ⊆ 批内文件后备份并原子应用；`batch_items` 记录 `attempt_id/base_hash/applied_hash`。`delegate_task` 波次模式由主 Agent 在 turn 内调用（结果 summary 上限 24k）。

**批次状态机（补充）**：`lease_expired→ ready` 后必须先做 `applied_hash/staged_path` 对账，再决定重派范围；`done` 前校验批内文件全部 `applied|manual`。

**与工作流节点的关系**：`batch` 节点 = 一个 BatchGroup；节点 `done` 条件 = 全批次 `done` + 聚合门通过；`batch` 节点内部不再嵌套 `batch` 节点（通过 split 子批表达）。

## 9. 多智能体协作协议

### 9.1 专家执行方式（按优先级）

| 优先级 | 方式 | 适用 | 说明 |
|---|---|---|---|
| 1 | `ctx.subagent_lifecycle.launch(SubagentLaunchRequest)` | 插件在活跃 turn 内 | 可等待/取消/转向，带 goal/context/role/model/toolsets/working_directory；受同源父会话治理；**无 output_schema、无单次 timeout、handle 进程内 1h** |
| 2 | `delegate_task` 工具（主 Agent 调用） | 对话式驱动 / 降级 | 插件产出 Turn Packet 文本，由主 Agent 委派；原生 output_schema；summary 上限 24k |
| 3 | 确定性脚本/命令 | 构建、类型检查等 | `script` 节点，不经 LLM |

### 9.2 Turn Packet 契约（防上下文膨胀的关键）

```json
{
  "run_id": "r-20261018-001",
  "node_id": "transform#42",
  "attempt": 2,
  "goal": "将 src/views/UserList.vue 迁移到 Vue3 Composition API",
  "slice": {
    "files": ["src/views/UserList.vue", "src/components/UserTable.vue"],
    "related": ["src/store/user.js"],
    "max_chars": 24000
  },
  "agent": {"id": "code-transformer", "prompt_ref": "agents/code-transformer.md"},
  "skills": ["vue3-transform", "vuex-to-pinia"],
  "experience": [{"id":"exp-17","trigger":"antdv scopedSlots","solution":"改用 #default 插槽","hit":6}],
  "constraints": {"style_guide": "prefer <script setup>", "language": "zh-CN"},
  "quality_target": {"pass": 85, "signals": ["ast","build","types"]},
  "budget": {"tokens": 60000, "timeout_s": 1800},
  "evidence_required": ["diff","notes"]
}
```
- 体积上限：默认 **32,000 字符**（不是字节；中文按字符计），超限按文件/组件边界截断并记录 `slice_truncated` 事件。子代理 `context` 上限亦为 32,000 字符（`subagent_lifecycle.py:223-224`）。
- 注入顺序：约束 > 当前切片 > 经验 > 历史（仅失败摘要）。

### 9.3 并发与冲突

- **专家并发**：同一专家可被多个 `parallel` 节点占用，但受 Run 级并发上限约束（默认 3）。
- **节点租约**：`lease_owner + lease_expires_at`；心跳每 30s；过期可被其他 driver 抢占（先写 claim token）。
- **资源冲突**：同一文件被多个节点写时，按依赖图串行；跨 Run 冲突通过文件级锁 + 人工提示。
- **专家跑偏**：输出必须符合 `output` 契约（文件/JSON schema）；不符合则判 `agent_drift`，取消并重派。

---

### 9.4 批量执行通道（FR-10）

| 通道 | API | 并发 | 批次控制 | 适用 |
|---|---|---|---|---|
| **生命周期子代理（首选）** | `ctx.subagent_lifecycle.launch/wait/cancel/result` | 进程内池 8（建议插件并发 ≤3） | 逐批 launch，可 per-launch `model/allowed_toolsets/correlation_id` | 插件自治批次循环 |
| `delegate_task` 批量（加速/降级） | `delegate_task(tasks=[...])`，主 Agent 在 turn 内调用 | 默认 10（`delegation.max_concurrent_children`）；**超限报错** | 一次调用一批批次（需按上限切波）；结果按 task index 排序 | 同层并行、主 Agent 汇总 |
| kanban dispatcher（P2） | 每批一张卡，dispatcher 起 worker | `max_concurrent` | 持久/跨进程/崩溃回收 | 超大规模、跨会话 |

**关键约束（设计已考虑）**
- `subagent_lifecycle` 需要活跃父会话；REST handler 不得直接 launch（见 §10.4 执行契约）。
- 两种通道都**不保证进程崩溃后 child 继续执行** → 批次 Checkpoint + staging/`applied_hash` 幂等是硬要求。
- **结果上限不同**：lifecycle 结果/context = 32,000 字符；`delegate_task` summary = **24,000 字符**（可配、受 headroom 影响）→ 批次结果契约按 24k 设计，逐文件 notes 精简。
- **结构化能力不同**：`lifecycle` **无 `output_schema`**（`structured_payload` 仅声明未实现）→ 提示词约束 + 插件 JSON 校验 + 一次格式纠正重派；`delegate_task` 原生 per-task `output_schema`。
- **写入治理**：child 以 `project_root` 为 cwd 读取源码、只写 `staging_root`；插件启动前记录工作区基线（git status/diff 或 hash 快照），结束后审计 `post - pre - 批内文件`，越界即回滚 + `agent_drift` + 人工门；审计通过后校验 staging 集合并原子应用（`write_mode=staging_apply`）。
- `delegate_task` 子代理继承父 toolsets、不能自定义；`lifecycle` 可用 `allowed_toolsets` 收窄 → 批次专家优先 lifecycle。
- 子代理不能交互（`clarify` 禁用），需要人判断时返回 `status=manual`，由插件生成人工门。

**Batch Packet**：见 FR-10 与 `research/batch-loop-analysis.md` §6.2；包含 `batch_id/index/total/wave/attempt/project_root/staging_root/files[{path,source_path,staging_path,hash}]/order/deps_summary/skills/experience/write_policy/result_contract/budget`，整体 ≤32,000 字符。`delegate_task` 通道收到结果后由 `flow_batch_ingest` 回灌插件（主 Agent 调用）。

## 10. 异常处理与自愈（实现细节）

### 10.1 异常分类器

输入：异常对象/错误码/退出码/响应头/子代理终止原因；输出：`kind + retryable + backoff + degrade_action + escalate_after`。

检测来源：
- LLM 调用：429/5xx/timeout/finish_reason=length/内容过滤。
- 工具：工具异常、命令退出码、构建错误。
- 子代理：`FAILED/INTERRUPTED/CANCELLED/UNKNOWN`、超时、结果超限。
- 编排：租约过期、写回冲突、依赖缺失、DAG 非法。
- 质量：低分、硬门失败、LLM 置信度低。

### 10.2 退避与熔断

- 指数退避 + full jitter：`min(cap, base * 2^attempt) * rand(0.5,1.0)`；429 遵 Retry-After。
- 连续失败熔断：节点级（N 次）/专家级（M 次）/全局（K 次）→ 暂停 Run 并告警。
- 降级链：模型降级（强→快）→ 上下文缩小 → 切片拆分 → 换专家 → 人工。

### 10.3 断点续跑

- 每次状态转换追加 `receipt` + 更新 `run_snapshot`（节点状态、attempt、证据引用、配额）。
- 进程重启：扫描 `running` 节点 → 租约过期 → 回滚到 `ready`（attempt+1）→ 幂等重放。
- 截断续跑：保留已产出的部分 diff/文件写入记录，`resume_from = last_completed_unit`。
- **批次续跑（FR-10）**：扫描过期批租约 → `ready` → 按 `applied_hash/staged_path` 对账：已应用文件跳过、staging 未应用文件重新校验应用、工作区内容不一致转 `manual`；已完成批次不重复执行。
- **不重复**：已完成节点不重跑；修复轮次保留历史证据。

### 10.4 心跳与无人值守（三种 driver，按环境选择）

| Driver | 机制 | 适用 | 说明 |
|---|---|---|---|
| **cron 心跳** | `hermes cron` 每 5 分钟跑 `hermes flow tick --resume`（prompt 指示 agent 调用 `flow_next_turn`） | 常驻/无人值守 | 最稳；但 cron 由 **gateway 内嵌 ticker** 驱动，gateway 未运行则无 tick（`architecture.md:165-174`） |
| **`/goal` 自续跑** | `/goal <完成目标>`，再 `/goal gate add hermes flow gate --run <id>`（该命令仅在 Run 成功时 exit 0） | 会话内长跑 | 复用 Hermes 原生 Ralph loop（aux 判 done/continue/blocked/wait + 确定性 shell 门 + `max_turns`）；**没有 `--gate` 参数**，gate 必须通过子命令添加 |
| **前台会话** | 用户打开会话，`flow_tick` 手动触发 | 调试/监督 | tick 必须在 **agent turn 内**执行；Dashboard 的"开始/继续"只创建 Run + 唤醒 cron + `ctx.inject_message` 通知，**不得**在 REST handler 直接 launch 子代理 |

**执行契约（实现必须遵守）**
- `ctx.subagent_lifecycle.launch()` 要求存在活跃父会话，否则抛 `No active Hermes parent session is available`（`agent/subagent_lifecycle.py:277-280`）；子代理只在进程内运行，进程退出后 `reconnect` 返回 `RECONNECT_UNAVAILABLE`。
- 因此 **REST/WS handler 永不直接 launch 子代理**；它们只做状态读写与"创建/唤醒 driver"。真正执行 turn 的只有三种 driver（cron 触发的 agent turn / `/goal` 会话 / 前台会话）。
- 无活跃会话时 Run 停在 `queued`，Dashboard 显示"下一步"引导（启动 gateway、创建 cron、或打开会话执行 `flow run --resume`）。
- `SubagentLaunchRequest` 的 `timeout_seconds` 当前被显式拒绝（`subagent_lifecycle.py:228`）；节点超时由插件用 `service.wait(handle, timeout_seconds=...)` + `cancel()` 自行管理。

- tick 逻辑：无活跃 driver → 取最早可运行 Run → 在 turn 预算内推进 → 干净退出（落 checkpoint）。
- 卡死检测：节点 running 超过 `timeout_s + grace` → 取消子代理 → 回收租约；heartbeat 每 30s。
- 上游限流/截断：优先由 Hermes `error_classifier`/`retry_utils` 处理；插件在节点级做退避与"换切片/换专家"。
- 通知：Dashboard 实时流 + 可选系统通知（人工门、失败、预算耗尽）；`ctx.inject_message` 可向父会话播报。

### 10.5 自循环终止条件（防死循环）

- 单节点 attempt 上限（默认 3）、回环上限（默认 3）、Run 总轮次上限、总 token/时间预算、连续无进展计数（3 次无状态变化 → 暂停）。
- 达到任一上限 → `human_gate`，给出可执行选项（重试/跳过/改配置/终止）。

---

## 11. 质量门控（实现细节）

### 11.1 评分流水线

```
evidence = collect(node)          # diff, build log, type errors, screenshots, console
signals = {
  ast:      parse_ok ? 100 : weighted_partial,
  build:    build_ok ? 100 : max(0, 100 - 15*errors),
  types:    type_errors == 0 ? 100 : max(0, 100 - 10*errors),
  browser:  page_ok && no_console_error ? 100 : partial_by_checklist,
  behavior: llm_review(score, confidence)     # 结构化 rubric
}
score = Σ(w_i * s_i); verdict = pass|warn|rework
```
- 每个信号必须给"证据引用"（命令、退出码、日志摘要/截图路径、LLM 原始结构化输出），缺证据的信号按 0 计。
- 硬门：`build=false` 或 `browser=白屏` → 直接 rework，不进入加权。
- LLM 评审 rubric：功能等价、模板语法、响应式数据、路由/状态、样式/主题、边界用例；输出 `{score, reasons[], confidence, blocking[]}`。

### 11.2 回环与升级

- rework：生成"修复 Turn Packet"，包含低分信号、证据、相关经验；最多 3 轮。
- 第 3 轮仍 <70 → `human_gate`，展示每轮分数与证据对比。
- 人工可：接受（记录为例外）、继续修复、调整阈值/权重、终止。

### 11.3 质量数据与校准

- 保存每次评分的 `scorer_version`、模型、prompt hash，便于回归比较。
- 抽样人工复核 → 计算 precision/recall → 调整权重（有审计记录）。
- 防"评分通胀"：复核发现假通过 → 降低该信号权重并要求重新门控。

### 11.4 分层门控（FR-10：批级 / wave / 聚合）

> 为什么必须分层：部分迁移状态下，全项目 `vite build`/`vue-tsc`/浏览器会因**尚未迁移的文件**失败；若批级执行全量硬门，第一批永远无法通过（死锁）。因此硬门后移。

| 层级 | 评分信号 | 硬门 | 执行时机 |
|---|---|---|---|
| **批级** | AST/parse、diff 与 staging 白名单、变更说明、可选 scoped 单测/局部类型检查、LLM 评审 | parse 失败、越界写、diff 超限 → 直接 rework | 每批完成后 |
| **wave 级（可选）** | 受影响模块增量构建、touched routes 浏览器 smoke | 该 wave 构建失败 → 该 wave repair，不影响其他 wave | 每个 wave 完成后 |
| **聚合级** | 全量 build、全量 type、浏览器 E2E、覆盖率、五信号加权 | 全量 build 失败 / 关键路由白屏 → 不通过 | 全部批次完成后一次 |

- 批级阈值可复用 85/70（权重按批内可用信号重新归一）；`quality_gate_per_batch=false` 时只做 parse/白名单硬检查，评分延后到聚合门。
- 聚合门通过条件：加权分 ≥85 **且** 覆盖率 100%（无 `pending/failed` 文件）**且** 全量 build 成功 **且** 关键路由无白屏。
- 全量 build/browser 只做一次聚合门（+ 可选 wave 增量），避免 43 次全量构建的成本。
- 越界写/`agent_drift` 属于批级硬失败，直接人工门，不参与加权。

---

## 12. 记忆系统设计

### 12.1 四层记忆

| 层 | 内容 | 存储 | 生命周期 | 回灌 |
|---|---|---|---|---|
| L1 Turn | 当前节点切片/约束/经验 | 内存 + packet | 单 turn | 直接注入 |
| L2 Run/工程 | Goal/Run/Node/Evidence/决策 | SQLite + checkpoint | 跨会话 | 状态查询 + refresh |
| L3 经验库 | 坑位/解法/适用版本 | SQLite FTS5 | 跨工程 | Top-K 检索注入 |
| L4 偏好 | 命名/风格/阈值/审批粒度 | 插件 config + Hermes 原生记忆 | 长期 | 每次 turn 注入约束 |

### 12.2 经验条目 schema

```json
{
  "id": "exp-00017",
  "category": "antdv-api-change",
  "trigger": "a-table scopedSlots 用法在 antdv 4.x 失效",
  "signals": ["scopedSlots", "a-table", "antdv"],
  "solution": "改用 #default / v-slot 插槽，slot-scope 迁移到 #default={...}",
  "stack": {"vue": "3.x", "antdv": "4.x"},
  "phase": "transform",
  "confidence": 0.86,
  "source": {"run_id": "r-...", "node_id": "transform#42", "agent": "修复专家"},
  "hit_count": 6,
  "status": "published",
  "created_at": "...", "last_seen": "..."
}
```

### 12.3 沉淀与召回

- **沉淀触发**：修复成功、人工标注、质量门连续两轮同因失败后修复成功。
- **去重**：归一化 trigger + category + stack；命中则 `hit_count++`、更新 `last_seen`、提升置信度。
- **召回**：按 `phase + skills + 文件特征` 检索；FTS5 关键词打分 × 置信度 × 新鲜度；Top-K（默认 5）注入 Turn Packet，超预算则只注入 trigger+solution 一行。
- **晋升**：`hit_count ≥ 5` 且人工确认 → 生成技能草稿（走技能 authoring 校验）。
- **质量**：自动沉淀为 `draft`，人工确认后 `published`；支持归档/合并重复条目。
- **批量场景**：经验按批次沉淀与召回——repair 子批优先召回同批/同文件类型的经验；批次成功后把"批内共性坑"合并为一条经验，避免 43 批产生 43 条重复经验。

### 12.4 与 Hermes 原生记忆的关系

- 不重复造"会话记忆"：会话历史/检索用 Hermes 原生能力。
- 工程结论/用户偏好可双写 Hermes 原生记忆（MEMORY.md），使普通对话也能受益。
- 经验库只存"结构化、可复用、可验证"的知识，避免污染通用记忆。

---

## 13. UI 设计

> 高保真设计稿：`ui-design/index.html`（可交互，8 屏）；截图 `ui-design/screenshots/*.png`；设计规范 `ui-design/design-spec.md`；还原提示词 `ui-design/PROMPTS.md`。

### 13.1 信息架构

```
HERMES Flow（Dashboard 页签 /flow）
├── 工作台 Workbench        Goal 总览 · 当前 Run · 批次进度 · 异常 · 快捷入口
├── 专家 Agents             列表/卡片 · 创建向导 · 详情抽屉 · 技能绑定 · 循环策略
├── 技能 Skills             技能库 · 新建/导入 · 校验 · 使用统计
├── 编排 Workflows          模板库 · DAG 画布 · 属性面板 · 版本 · batch 节点
├── 监控 Runs               实时看板 · 批次队列 · 节点详情 · 证据 · 时间轴 · 回放
├── 记忆 Memory             经验库 · 偏好 · 工作区记忆
├── 质量 Quality            评分看板 · 批次下钻 · 低分列表 · 回环记录 · 校准
└── 设置 Settings           内核 · 模型 · 并发/配额 · 批量参数 · 阈值 · 诊断
```

### 13.2 设计语言（V2）

- **气质**：工程控制台 / 作战室（Mission Control），不是营销页。信息密度高、层级清晰、状态语义强。
- **色彩（以设计稿实际实现为准）**：应用底 `#07090B`；侧栏 `#0A0D10→#080B0E`；面板 `#0F1419→#0D1217`；一级文本 `#E6EDF3`、二级 `#A9B5C1`、三级 `#8B97A4`；品牌信号色 `#35CFC1`（运行/交互/进度）；状态色：通过 `#56C98A`、警告/回环 `#E0A93E`、失败/人工门 `#E9695F`、信息 `#5E9CF5`、空闲 `#8B97A4`。完整 tokens 见 `ui-design/design-spec.md` §3。
- **字体**：系统 sans（中文优先） + 等宽 `JetBrains Mono` 回退（数据/日志/代码）。
- **栅格**：左侧导航 236px + 主区（最大宽 1680px）；技能/质量等页采用 3–9 分栏；卡片圆角 12px；间距 4/8/12/16/24/32；1560–1600px 视口下信息密度最佳。
- **可访问性**：对比度 ≥ WCAG AA；键盘可达（Tab/Enter/Esc）；焦点环可见；状态不只靠颜色（图标+文字）。

### 13.3 关键页面（验收级描述）

1. **工作台**：顶部 4 个 KPI（目标文件、已完成、质量通过率、活跃异常）；当前 Run 卡增加**批次进度**（`批次 18/43 · 文件 126/287`）；中部当前 Run 的 DAG 缩略 + 进度；右侧异常流与"今日经验"；底部最近 Run 表。
2. **专家**：卡片网格（头像/首字母、名称、角色摘要、技能 chips、状态点、成功率小环、**循环徽标 `循环 · 7 文件/批`**）；顶部搜索/筛选/新建；右侧详情抽屉（提示词、技能、运行记录、**批次循环配置**、编辑）。
3. **技能**：左侧阶段筛选（analyze/deps/transform/quality/verify/fix），中间技能卡（名称、描述、绑定数、最近使用），右侧预览（Markdown 渲染 + frontmatter 校验结果）。
4. **编排**：三栏（节点库/画布/属性）；画布支持缩放、框选、自动布局、运行态高亮；**batch 节点显示 `×N 批`，属性面板含批量源/批大小/并发/内层循环/失败拆分**；顶部校验/试运行/发布；底部变更记录。
5. **监控**：Goal 头 + 进度环；DAG 运行态（当前节点脉冲动画）；**批次队列面板（按 wave 分组，显示批号/文件数/状态/评分，可展开批内文件）**；专家状态矩阵；时间轴/日志（含 `batch.claim/ingest/gate/split/retry` 事件）；点击节点/批次开证据抽屉（批次汇总 + 文件级 diff/构建/截图/评分）。
6. **记忆**：经验卡片流 + 搜索/筛选；卡片展开显示触发/解法/来源/命中；右侧"偏好"面板；底部"晋升技能"候选。
7. **质量**：评分分布直方图、五信号均值条形、**批次通过率与按批次分组下钻**、低分 Top 10 表、回环记录时间线、校准开关；"重新审查"按钮可针对当前批次触发。
8. **设置**：内核选择（SQLite/LoopX，带状态检测）、模型与委派、并发/配额、**批量执行（默认批大小/最大并发批次/每 tick 批数/单批等待超时/拆分策略/上下文预算）**、门控阈值与权重（滑块+数字）、证据保留、诊断（插件 doctor 输出）、危险区（清理数据）。

### 13.4 与 Hermes Dashboard 的集成方式

- 标准 Dashboard UI 插件：`dashboard/manifest.json` → `tab: {path:"/flow", position:"after:skills"}`，`entry: dist/index.js`，`css`，`api: plugin_api.py`。
- UI 使用 Dashboard 暴露的 Plugin SDK（`window.__HERMES_PLUGIN_SDK__`）获取当前主题/用户/导航能力；**不自建壳、不 fork Dashboard**。
- **设计稿说明**：`ui-design/index.html` 为便于评审的"独立演示壳"（自带侧栏/顶栏/8 页导航）；落地时映射为 `/flow` tab 内的 8 个子页，复用宿主侧栏/顶栏，仅保留子页内容区（详见 `ui-design/design-spec.md`）。演示壳与落地壳的差异不改变设计 tokens 与组件规范。
- 后端 API 统一前缀 `/api/plugins/hermes_flow/`；实时事件走 WebSocket `/ws`（同前缀）。
- 降级：若 Dashboard 不可用，CLI `hermes flow status --watch` 与 `board_render` 生成的自包含 HTML 看板仍可用。
- 截图说明：`ui-design/screenshots/*.png` 为 1600×1000 视口截图（非 full-page），设置/质量页底部可能有滚动裁切；完整页面以 `index.html` 为准。

---

## 14. 实现方式

### 14.1 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 插件宿主 | Hermes 插件（Python 3.14） | 与 Hermes 同进程，直接用 `ctx` API |
| 状态内核 | SQLite（WAL）+ JSON checkpoint | 零外部依赖、事务原子认领、可移植 |
| 工作流引擎 | 纯 Python（拓扑排序 + 状态机） | 轻量、可测、无第三方依赖 |
| Dashboard UI | 单文件预构建 JS bundle（推荐 React 18 + Vite）+ 原生 CSS | 与 Dashboard 技术栈一致；drop-in 无需用户构建；先交付可用的 vanilla/React 原型 |
| Dashboard 后端 | FastAPI router（`plugin_api.py`） | Hermes 官方插件契约 |
| 浏览器验证 | Playwright（Node 侧）或 Hermes browser 工具 | 复用已有浏览器资产 |
| 评分脚本 | Node 子进程（`@vue/compiler-sfc`、`vue-tsc`、`vite`） | 前端生态标准工具 |
| 记忆检索 | SQLite FTS5（可选向量扩展） | 零依赖、够用 |
| 批次调度 | 纯 Python（拓扑分层 + 预算装箱 + 租约队列） | 复用前序 topo；无需第三方调度器 |
| LoopX 适配 | CLI 子进程桥接 + JSON 输出解析（单写者、失败降级） | LoopX 稳定契约是 CLI+JSON，Python 内核不可外部 import |

### 14.2 插件包结构

```
E:\hermes\plugins\hermes_flow\
├── plugin.yaml                  # name/version/kind/provides_tools/provides_hooks
├── __init__.py                  # register(ctx): tools + cli + commands + hooks + skills
├── core/
│   ├── registry/                # agent.py skill.py workflow.py（加载/校验/CRUD）
│   ├── engine/                  # dag.py scheduler.py turn.py state_machine.py
│   ├── batch/                   # planner.py queue.py loop.py split.py（拓扑分层+预算装箱+批次循环）
│   ├── quality/                 # scoring.py gate.py signals/（ast/build/types/browser/behavior）
│   ├── recovery/                # classify.py backoff.py checkpoint.py policy.py
│   ├── memory/                  # experience.py recall.py preferences.py
│   ├── kernel/                  # protocol.py sqlite_kernel.py loopx_kernel.py models.py
│   └── store/                   # db.py migrations/ schema.sql
├── agents/                      # 内置专家模板（yaml/md）
├── skills/                      # 内置技能（SKILL.md）
├── workflows/                   # 内置工作流模板（JSON）
├── dashboard/
│   ├── manifest.json            # tab / entry / css / api
│   ├── dist/index.js            # 预构建 UI bundle
│   ├── dist/style.css
│   └── plugin_api.py            # FastAPI router（/api/plugins/hermes_flow/*）
├── cli/                         # `hermes flow` 子命令
├── tests/                       # 单测 + 集成测试
└── README.md
```

**用户数据目录**（跨升级保留，使用官方 `plugin_data_dir("hermes_flow")` → `$HERMES_HOME/plugin-data/hermes_flow/`；**禁止写插件安装目录**）：
```
plugin-data/hermes_flow/
├── config.json                  # 阈值/并发/内核/模型（也可走 ctx.get_config/set_config）
├── agents/*.json                # 用户专家
├── workflows/*.json             # 用户工作流
├── state.db                     # 运行态（SQLite WAL：Goal/Run/Node/Evidence/Experience）
├── checkpoints/<run>/*.json     # 断点
├── evidence/<run>/<node>/       # diff/日志/截图
└── events/<run>.jsonl           # 事件流（WebSocket 补发数据源）
```
**用户技能**：写标准 `$HERMES_HOME/skills/<name>/SKILL.md`（走 Hermes 原生发现）。注意 `skills.write_approval` **只门控 `skill_manage` 工具**的写入，插件直接 `write_text` 不经过该门控 → 插件自身必须做 frontmatter 校验、备份与审计，并在 UI 明示"由 HERMES Flow 写入"；若在 agent turn 内，可优先 `ctx.dispatch_tool("skill_manage", ...)` 走原生审批。**内置技能**用 `ctx.register_skill(...)` 注册为只读 `plugin:skill`，不写用户技能目录。

### 14.3 插件注册清单（`register(ctx)`）

```python
def register(ctx):
    # 1) 加载注册表（内置 + 用户，自动加载）
    registry = Registry.load(ctx)
    # 2) 工具（toolset 名不要与内置冲突）
    for name, schema, handler in flow_tools(registry):
        ctx.register_tool(name=name, toolset="hermes_flow", schema=schema, handler=handler)
    # 3) CLI / slash
    ctx.register_cli_command("flow", help="HERMES Flow control plane", setup_fn=cli.setup, handler_fn=cli.run)
    ctx.register_command("flow", handler=slash.flow, description="查看/恢复迁移工作流")
    # 4) 技能（内置技能 → 只读 plugin:skill 命名空间）
    for skill in registry.builtin_skills:
        ctx.register_skill(skill.name, str(skill.path), skill.description, skill.frontmatter)
    # 5) hooks / middleware
    ctx.register_hook("pre_tool_call", hooks.pre_tool_call)          # 受保护写/预算门
    ctx.register_hook("post_tool_call", hooks.post_tool_call)        # 结果记账
    ctx.register_hook("subagent_stop", hooks.subagent_stop)          # 子代理结束回收
    ctx.register_hook("pre_verify", hooks.pre_verify)                # 无验证证据不放行
    ctx.register_hook("pre_llm_call", hooks.pre_llm_call)            # 经验召回注入（≤10k）
    ctx.register_middleware("tool_execution", middleware.tool_exec)  # 超时/异常包裹
    # 6) 每轮启动恢复：租约过期 → re-ready（幂等）
    recovery.bootstrap_resume(registry, ctx)
```
> 注：`ctx.register_skill` 签名以 `plugins_content.py:22-52` 为准；hook 名以 `plugins.py:109-204` 的 `VALID_HOOKS` 为准；若目标版本缺某 hook，按"能力探测 + 降级"实现，不阻塞核心功能。

> 以上方法名以 `research/hermes-capabilities.md` 第 2 节的源码证据为准；若某 hook 名在当前版本不存在，按"能力探测 + 降级"实现（不阻塞核心功能）。

### 14.4 工具清单（首批 40 个 / 11 组）

| 工具 | 用途 |
|---|---|
| `flow_agent_create/list/get/update/delete` | 专家 CRUD（prompt→agent，技能绑定，loop_policy） |
| `flow_skill_create/list/validate` | 技能创建/校验（写标准 SKILL.md） |
| `flow_workflow_create/list/get/validate/instantiate` | 工作流 CRUD 与模板实例化 |
| `flow_run_start/pause/resume/cancel/status` | Run 生命周期 |
| `flow_next_turn/claim/complete/fail/heartbeat` | 调度原语（供 driver/主 Agent 调用） |
| `flow_batch_plan/next/claim/ingest/complete/fail/split/status` | **批次规划、循环调度、结果回灌（FR-10）** |
| `flow_gate_score/decide` | 质量评分与门判定（批级/聚合） |
| `flow_recovery_classify/checkpoint` | 异常分类与检查点 |
| `flow_experience_add/search` | 经验沉淀与召回 |
| `flow_preferences_get/set` | 用户偏好 |
| `flow_board_render` | 生成自包含 HTML 看板（降级） |

每个工具：JSON Schema 入参、结构化 JSON 出参、错误码（`FLOW_*`）、幂等键、超时与大小上限；写操作要求 `expected_version`。

### 14.5 Dashboard API（prefix `/api/plugins/hermes_flow`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/agents` `/agents/{id}` | 专家列表/详情 |
| POST/PUT/DELETE | `/agents` `/agents/{id}` | 专家 CRUD |
| GET/POST | `/skills` | 技能列表/创建/导入 |
| GET/POST | `/workflows` | 工作流列表/创建 |
| POST | `/workflows/{id}/validate` `/instantiate` | 校验/模板实例化 |
| POST | `/runs` | 创建 Run（goal + workflow + project_root） |
| POST | `/runs/{id}/pause|resume|cancel` | 控制 |
| GET | `/runs/{id}/batches` `/batches/{id}` `/batches/{id}/items` | **批次队列/批内文件状态（FR-10）** |
| POST | `/batches/{id}/retry|split|skip` | 批次重试/拆分/跳过 |
| POST | `/batches/{id}/ingest` | **回灌 `delegate_task` 波次结果（逐文件结果入账）** |
| POST | `/batches/{id}/apply` | **校验 staging 并原子应用到工作区** |
| GET | `/runs/{id}` `/runs/{id}/nodes` `/runs/{id}/evidence` | 状态/节点/证据 |
| GET | `/ws?run_id=&ticket=` | WebSocket 实时事件（续传用 `last_event_seq`；鉴权走 query ticket，参照 kanban 先例） |
| POST | `/gates/{id}/decide` | 人工门决策 |
| GET/POST | `/experience` | 经验检索/沉淀 |
| GET/PUT | `/settings` | 配置（阈值/并发/内核/模型） |
| GET | `/diagnostics` | 自检（版本/内核/运行时/磁盘） |

安全：默认仅本机 loopback；写操作校验来源（同源）+ CSRF token；不返回密钥；危险操作审计。
部署约束：`plugin_api.py` 的 `router` 挂载到 `/api/plugins/hermes_flow`。v0.22.2 对**新增/新启用插件**有 hot-mount fallback（首次请求时 force_rescan 后现场挂载）；只有**已挂载路由的代码变更**才需重启 `hermes dashboard`。前端资源可用 `GET /api/dashboard/plugins/rescan` 热重扫。若插件未启用或未授权，路由不会挂载（fail-closed），UI 显示"插件未启用/未挂载"引导。

### 14.6 数据模型（核心表）

```sql
-- goals: 迁移目标
CREATE TABLE goals(id TEXT PRIMARY KEY, title TEXT, description TEXT, project_root TEXT,
  status TEXT, created_at INTEGER, updated_at INTEGER);
-- runs: 一次执行
CREATE TABLE runs(id TEXT PRIMARY KEY, goal_id TEXT, workflow_id TEXT, workflow_version TEXT,
  kernel TEXT, status TEXT, current_node TEXT, progress REAL, started_at INTEGER, ended_at INTEGER,
  snapshot_json TEXT, schema_version INTEGER);
-- nodes: 运行节点
CREATE TABLE nodes(id TEXT PRIMARY KEY, run_id TEXT, node_key TEXT, type TEXT, name TEXT,
  agent_id TEXT, status TEXT, attempt INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 3,
  lease_owner TEXT, lease_expires_at INTEGER, score REAL, verdict TEXT,
  input_json TEXT, output_json TEXT, updated_at INTEGER);
-- evidence: 证据（追加式）
CREATE TABLE evidence(id TEXT PRIMARY KEY, run_id TEXT, node_id TEXT, attempt INTEGER,
  kind TEXT, path TEXT, summary TEXT, score REAL, meta_json TEXT, created_at INTEGER);
-- gates: 门（可精确到批次）
CREATE TABLE gates(id TEXT PRIMARY KEY, run_id TEXT, node_id TEXT, batch_id TEXT, kind TEXT, question TEXT,
  status TEXT, decision TEXT, decided_by TEXT, decided_at INTEGER, payload_json TEXT);
-- checkpoints
CREATE TABLE checkpoints(id TEXT PRIMARY KEY, run_id TEXT, node_id TEXT, attempt INTEGER,
  state_json TEXT, created_at INTEGER);
-- batch_groups: 一个 batch 节点的运行实例（FR-10）
CREATE TABLE batch_groups(id TEXT PRIMARY KEY, run_id TEXT, node_id TEXT, expert_id TEXT,
  total_files INTEGER, total_batches INTEGER, done_batches INTEGER DEFAULT 0,
  aggregate_score REAL, aggregate_verdict TEXT,
  status TEXT, policy_json TEXT, created_at INTEGER, updated_at INTEGER);
-- batches: 最小子任务
CREATE TABLE batches(id TEXT PRIMARY KEY, group_id TEXT, wave INTEGER, seq INTEGER,
  status TEXT, attempt INTEGER DEFAULT 0, split_depth INTEGER DEFAULT 0,
  files_json TEXT, workspace_baseline_json TEXT,
  score REAL, verdict TEXT,
  lease_owner TEXT, lease_expires_at INTEGER, version INTEGER DEFAULT 0,
  agent_correlation_id TEXT, started_at INTEGER, ended_at INTEGER);
-- batch_items: 文件级幂等（唯一事实源）
CREATE TABLE batch_items(id TEXT PRIMARY KEY, group_id TEXT, batch_id TEXT, file_path TEXT,
  status TEXT, attempt_id TEXT, base_hash TEXT, staged_path TEXT, applied_hash TEXT,
  attempts INTEGER DEFAULT 0, evidence_json TEXT, updated_at INTEGER,
  UNIQUE(group_id, file_path));
-- batch_receipts: 批次审计/续跑
CREATE TABLE batch_receipts(id TEXT PRIMARY KEY, batch_id TEXT, attempt INTEGER,
  event TEXT, payload_json TEXT, created_at INTEGER,
  UNIQUE(batch_id, attempt, event));
-- experiences
CREATE TABLE experiences(id TEXT PRIMARY KEY, category TEXT, trigger TEXT, solution TEXT,
  stack_json TEXT, phase TEXT, confidence REAL, hit_count INTEGER, status TEXT,
  source_json TEXT, created_at INTEGER, last_seen INTEGER);
-- leases / receipts / quotas / events 同理
```

- `PRAGMA journal_mode=WAL`；写操作单事务；`claim` 用 `UPDATE ... WHERE status='ready' AND (lease_expires_at IS NULL OR lease_expires_at < :now)` 的 rowcount 保证原子（NULL 处理必须显式，否则新行永远 claim 不到）。
- **批次幂等**：`batch_items` 以 `(group_id, file_path)` 唯一；`attempt_id` 约束当前写回；`applied_hash` 用于续跑对账；批次 `done` 前校验批内文件全部 `applied|manual`。
- 索引：`batches(group_id,status)`、`batch_items(batch_id)`、`batch_items(group_id,status)`、`batch_receipts(batch_id)`。
- **越界审计**：`batches.workspace_baseline_json` 保存启动前 git status/diff（或 hash 快照）；结束后 `post - pre - 批内文件` 必须为空，否则回滚并转人工。
- **并行批应用**：同 wave 并行批各自在独立 worktree/staging 执行；**apply 必须串行化**（单写者队列），冲突文件 → 人工门，禁止并发写同一工作区。
- **覆盖率口径**：聚合门覆盖率 = `applied / total`；`manual` 文件不计入通过，存在 `manual` 时 Run 停在 `waiting_gate`，人工确认后才允许聚合门判定。
- schema 版本化（`schema_version` + 迁移脚本）。

### 14.7 复用前序资产

| 前序资产 | v2.2 处理 |
|---|---|
| `vue3migrate_core/kernel`、`engine`、`quality`、`recovery`、`experience` | 迁入 `core/` 并扩展（五原语已有，补租约/心跳/WebSocket 事件） |
| 7 个迁移技能 | 作为内置技能包（`skills/vue3-*`），保留并补充 `vue3-router4`、`vue3-antdv`、`vue3-vite` |
| 16 个工具 | 重命名为 `flow_*` 并补 CRUD/UI 所需接口；保留兼容别名一个版本 |
| `board_render` HTML 看板 | 保留为降级方案 |
| `vue3_migration` 旧插件 | 标记 deprecated，提供迁移指南；v2 安装后自动检测并提示 |

---

## 15. 实施计划（5 个核心里程碑 + 1 个可选，约 35–50 人日）

> 说明：35–50 人日为"可上线硬化版"（UI 5–8 / 引擎 6–8 / **批次调度 4–6** / 评分与证据 6–8 / 恢复与租约 4–6 / 记忆 3–4 / LoopX 桥接 4–6 / 测试与文档 5–8）。
> 若先做"可演示 MVP（假数据 UI + 单链路引擎 + 批次循环）"，约 15–18 人日。

| 里程碑 | 范围 | 交付物 | 验收 |
|---|---|---|---|
| M0 环境与骨架（1–2 天） | 修复 Hermes 运行时；插件骨架 + doctor 通过；`plugins enable` + capability consent；Dashboard tab 空页 + hot-mount 验证 | `plugin.yaml`、`register()`、`dashboard/manifest.json`、`plugin_api.py` | `hermes plugins doctor` 通过；`/flow` 页签可见；`/api/plugins/hermes_flow/diagnostics` 返回 200 |
| M1 注册中心 + 专家/技能 UI（3–4 天） | Agent/Skill Registry、CRUD、自动加载、技能校验、专家/技能两屏、**专家 loop_policy** | 工具 + API + UI | 创建→重启→仍在；技能可绑定并注入 |
| M2 工作流引擎 + 编排/监控 UI（6–8 天） | DAG DSL、调度器、状态机、租约/心跳、Run API、WebSocket、编排与监控两屏、**批次规划器 + 批次队列/批量节点** | 引擎 + batch + 工具 + UI | 六阶段模板跑通；串行硬约束；**287 文件切成约 43 批**；实时看板 |
| M3 质量门控 + 异常自愈（4–5 天） | 五信号评分、批级/聚合门、回环、异常分类/退避/checkpoint、**批次拆分/repair/断点续跑**、恢复 UI | 评分器 + 恢复编排 + 质量屏 | 注入 429/截断/重启均能续跑；低分回环；**只重跑失败批次/文件** |
| M4 记忆/经验 + 设置 + 端到端（3–4 天） | 经验库/偏好、设置页（含批量参数）、样例项目 E2E、报告、文档 | 全功能 + E2E 报告 | 20 文件与 287 文件样例全绿；连续 2h 无人值守 |
| M5（可选）LoopX 适配 + 无头 daemon | LoopX adapter、`hermes flow daemon`、多 harness | 可选集成 | 两内核状态一致；daemon 可跑 |

**并行分工（Agent Teams）**：注册中心/内核（1 人）、引擎/调度（1 人）、**批次调度（1 人）**、评分/恢复（1 人）、Dashboard UI（1 人）、技能/模板内容（1 人）、测试与 E2E（1 人）。写作用域按目录切分（`core/kernel`、`core/engine`、`core/batch`、`dashboard/`、`skills/`、`tests/`），避免冲突。

---

## 16. 验收标准

### 16.1 功能验收（MVP）

- [ ] 专家：提示词创建、技能绑定、重启恢复、导入导出、引用保护。
- [ ] 技能：标准 SKILL.md 创建/校验/导入，绑定后可被实际注入。
- [ ] 工作流：可视化搭建、校验、模板实例化、版本化、导入导出。
- [ ] 运行：实时状态（≤1s）、进度、节点证据、历史回放、断线重连。
- [ ] 质量：五信号评分、门控、回环、硬门、证据链、报告。
- [ ] 恢复：429/截断/超时/进程重启四类故障演练通过。
- [ ] 记忆：经验沉淀/去重/检索/回灌/晋升；偏好生效。
- [ ] 集成：`hermes plugins enable/doctor` 正常；Dashboard tab 正常；CLI 正常。
- [ ] LoopX：`--backend loopx` 契约测试通过、缺失时自动降级、无双写（FR-8）。
- [ ] 运维：设置/诊断/数据导出清理、升级不丢数据、插件禁用后 UI 引导（FR-9）。
- [ ] **批量循环（FR-10）**：287 文件切成约 43 批；每批一个子代理；批内循环、批间串行；失败只重跑失败批/文件；截断自动拆批；429 波次暂停恢复；杀进程后续跑；1000 文件计划可复现。

### 16.2 质量指标（SLO）

| 指标 | 目标 | 统计方法 |
|---|---|---|
| 节点状态一致性（UI vs 内核） | 100% | 随机 50 个时点抓取 UI 快照与 `/runs/{id}` JSON，字段级 diff；不允许差异 |
| 事件延迟（写回→UI） | P95 ≤ 1s（本机） | 埋点记录 `event.created_at` 与前端收到时间，1000 次事件取 P95 |
| 断点续跑成功率 | 100 次中断演练中 ≥99 次成功（95% 置信下界 ≈95%） | 脚本随机杀进程/注入断连 100 次，统计成功恢复且无重复节点 |
| 已完成节点重复执行率 | 0（幂等） | 每次恢复后比对 `receipt`，重复执行即失败 |
| 质量评分可追溯率 | 100% | 每条评分必须能定位到证据文件/命令输出；抽样 100 条核对 |
| 无人值守连续运行 | ≥ 2h（样例项目） | cron/gateway 连续运行，记录中断次数与原因 |
| 插件加载耗时 | ≤ 2s（不含 LLM） | `hermes plugins doctor` + 启动日志时间差 |
| Dashboard 首屏 | ≤ 1.5s（本机） | 浏览器 performance timing，冷/热各 5 次取中位数 |
| **批次完成率（287 文件）** | 100%（约 43 批全部 done） | 统计 `batches` done/total 与文件覆盖率 |
| **已完成文件重复处理率** | 0 | 恢复后比对 `applied_hash`，重复应用即失败 |
| **同 wave 失败隔离率** | 100% | 注入单批失败，检查同 wave 互不依赖批是否继续；依赖批按策略阻塞（预期行为） |
| **批次结果解析成功率** | ≥99% | lifecycle 文本 JSON 校验 + 一次格式纠正重派；统计成功/总数 |
| **driver 单例** | 100% | 双 cron/会话同时 tick，验证只有持锁者推进、无重复认领 |
| **100 批连续运行（注入 10 次故障）无人介入完成率** | ≥95% | 脚本注入 429/截断/重启，统计最终 success；且不超 Run 总 token/时长预算 |
| **Run 总预算** | 100% 不超支 | 每次 tick 记录 token/时长；超 80% 告警、超 100% 暂停并人工门 |

**评分基线（样例项目 20 文件，验收用）**

| 指标 | 期望值 | 允许误差 | 说明 |
|---|---|---|---|
| 总评分（加权） | 85–95 | ±5 | 首次通过；低于 85 应有明确低分证据 |
| AST | 100 | 0 | 迁移后必须全部可解析 |
| 构建 | 100 | 0 | `vite build` exit 0 |
| 类型 | ≥95 | ±5 | 允许既有类型告警 |
| 浏览器 | ≥90 | ±10 | 白屏/控制台 error 直接不通过 |
| 行为一致性（LLM 评审） | ≥80 | ±10 | 需人工抽样复核 20% |
| 低分回环触发 | 至少 1 次 | — | 故意保留 1 个 antdv/ztree 坑位验证回环 |
| 经验命中 | ≥1 条 | — | 第二个相似文件应命中第一条经验（A/B：无经验 vs 有经验，各 10 次转化，命中率 ≥80% vs ≤20%） |

### 16.3 测试矩阵

- 单元：DAG 校验/拓扑、状态机非法迁移、原子 claim（含 NULL 租约）、退避计算、评分权重、经验去重、SQL 迁移。
- 集成：插件加载、工具调用、API、WebSocket（鉴权/续传）、Checkpoint/restore、内核切换、hot-mount。
- E2E：20 文件样例 → 六阶段 → 全绿；注入故障（429/截断/杀进程/浏览器崩溃）→ 自愈。
- 兼容：Hermes 升级回归（manifest v1/v2、`api_version`、插件 API 探测）。
- 安全：同源/CSRF、未启用插件 404、路径穿越、密钥不落库、危险操作人工门。
- 平台：Windows 路径/长路径/中文路径、权限不足、Node/Python 工具链缺失降级。
- 迁移：旧插件 `vue3_migration` 数据导出/导入、并存/禁用引导。
- 可测性：`/goal gate add` 退出码契约、`flow status --strict`、无活跃会话时 Run queued 引导。
- **批量**：1000 文件计划生成/依赖安全；287 文件全批 E2E；同 wave 隔离/依赖阻塞；截断拆批；429 波次退避；杀进程按 applied_hash 续跑；越界写拒绝回滚；lifecycle 结果校验/格式纠正；driver 单例；同层并行 worktree 隔离；上下文 ≤32k、delegate 结果 ≤24k；批次 UI 一致性；100 批 10 故障压测 + 总预算。

### 16.4 演练脚本（Demo）

1. 新建专家「代码转化专家」+ 绑定技能 → 重启 → 仍在。
2. 从模板创建 Goal → 启动 Run → 看板推进。
3. 注入 429 → 观察退避 → 自动恢复。
4. 注入低分文件 → 观察修复回环 → 评分提升。
5. 杀进程 → 重启 → Resume → 不重复。
6. 查看质量报告与经验沉淀 → 下一个相似文件命中经验。
7. **批量循环**：导入 287 文件项目 → 触发生成 43 批 → 观察批次队列推进（批 18/43）→ 注入单批失败 → 只 repair 该批 → 最终聚合门通过。

---

## 17. 风险与开放问题

| 风险 | 影响 | 缓解 |
|---|---|---|
| Hermes 插件 API 有 `api_version` 字段但无强制兼容承诺，升级可能变动 | 插件失效 | 能力探测 + 降级；锁 `requires_hermes`；CI 回归 |
| 本机运行时损坏（`tools\python` ACL 拒绝） | 无法验收 | 先跑 `setup-hermes.ps1 -RuntimeOnly` 修复；修复前用 pm-runtime Python 只读验证；`hermes doctor` 自检 |
| 已挂载的 `plugin_api.py` 代码变更需重启 web server（新增插件可 hot-mount） | UI 更新不即时 | 开发/升级后重启 `hermes dashboard`；前端 rescan；UI 显示"未启用/未挂载"引导 |
| cron 依赖 gateway 运行 | 无人值守驱动失效 | 启动 gateway；Dashboard 显示 driver 状态；提供 `/goal` 与前台会话两种备选 |
| 社区 `hermes-workflows` 功能重叠 | 重复造轮子/用户困惑 | 明确差异化（迁移领域门控/专家/经验库/中文 UI）；文档给共存说明；不复制其代码 |
| 插件 capabilities 未授权 | 功能被拒（如 tools.override） | 不替换内置工具，用 `flow_*` 新命名；必要时声明 capabilities 并走同意屏 |
| LoopX 版本漂移 / Node 硬依赖 | 桥接失效 | pin 版本 + `loopx doctor` + 契约测试；失败自动降级；默认不启用 |
| 长时运行受上游限流/超时 | 任务中断 | Turn 预算 + checkpoint + cron 心跳 + 退避 |
| 评分误判（假通过/假失败） | 质量风险/返工 | 硬门 + 证据链 + 抽样复核 + 权重校准 |
| 上下文仍可能超限 | 转化质量下降 | 按 AST/组件边界切片 + 经验压缩注入 |
| 自愈死循环 | 资源浪费 | 多级上限 + 无进展检测 + 人工门 |
| Dashboard bundle 构建复杂 | 交付延期 | 先用单文件 vanilla/React 预构建；无构建步骤 |
| LoopX 上游不稳定 | 集成风险 | 默认自研内核；LoopX 仅可选 |
| 多并发写冲突 | 状态错乱 | 租约 + 乐观锁 + 文件级串行 |
| 数据/密钥安全 | 泄露 | 本地存储、不记录密钥、API 同源校验、审计 |
| **批次过多导致启动开销/成本上升** | 时长/费用 | 自适应批大小（成功后放大、截断即拆）；上限 12；启动开销约 2–4k token/批 |
| **批次过大导致上下文截断** | 质量下降 | 预算装箱（28k）；截断二分拆批；single_file 兜底 |
| **同层并行破坏依赖/写冲突** | 构建失败/覆盖 | 仅同 wave 并行；默认串行；依赖闭包校验；**并行批独立 worktree/staging，串行合并** |
| **子代理越界改批外文件** | 污染/回滚困难 | **只写 staging + 白名单对账 + 拒绝 apply + agent_drift + 人工门** |
| **写后崩溃重复转换** | 覆盖人工修改 | **staging + applied_hash 账本 + attempt_id + 租约对账** |
| **lifecycle 无 output_schema** | 结果不可解析 | 提示词约束 + 插件 JSON 校验 + 一次格式纠正重派；仍失败转 single_file/人工 |
| **delegate 结果 24k 截断** | 丢文件/重复处理 | 结果契约按 24k 设计；逐文件 notes 精简；超限拆批 |
| **多 driver 并发/心跳中断** | 重复认领/超并发 | **Run 级 driver 单例锁 + 独立 heartbeat + wait 分片** |
| **handle 跨进程/超 1h 丢失** | 批次卡住 | 租约过期 → ready → applied_hash 对账 → 重派未应用文件 |
| **批级全量构建死锁** | 第一批无法通过 | **批级只做 AST/diff + 白名单；全量 build/browser 只在聚合门** |

**开放问题（不阻塞，默认值已定）**
1. 是否接受"单插件内置 Vue3 领域包"（默认是；未来可拆分为独立 domain pack）。
2. 默认并发数（默认 3）与 turn 预算（默认 10 分钟/20 节点/次 tick）是否合适。
3. 评分权重/阈值是否按项目可配（默认可配，管理员权限）。
4. 是否需要支持多项目并行（默认支持多 Goal，但同项目文件级串行）。
5. **批量默认值**：每批 7 文件、并发 1、每 tick 10 批、单批 wait 1800s、拆分深度 2（详见 FR-10）；可按项目覆盖。

---

## 附录 A：Vue2→Vue3 六阶段工作流模板（内置）

| 阶段 | 专家 | 技能 | 输入 | 输出 | 门 |
|---|---|---|---|---|---|
| 1 分析 analyze | 结构分析专家 | `vue3-analyze` | 项目根 | 文件清单、技术栈、风险、迁移点统计 | — |
| 2 依赖 deps | 依赖分析专家 | `vue3-deps` | 分析报告 | 依赖图、版本矩阵、升级方案、批次拓扑序 | 依赖完整性检查 |
| 3 转化 transform | 代码转化专家 | `vue3-transform` + `vuex-to-pinia` + `vue3-router4` | 批次切片 | 代码 diff、转化说明 | AST 门 |
| 4 质量 quality | 质量分析专家 | `vue3-quality` | diff | 五信号评分、证据 | 质量门（85/70） |
| 5 验证 verify | 浏览器验证专家 | `vue3-verify` | 构建产物 | 渲染/交互/截图/控制台 | 浏览器硬门 |
| 6 修复 fix | 修复专家 | `vue3-fix` | 低分证据 | 修复 diff、经验草稿 | 回环 ≤3 轮 |
| 终 人工验收 | 迁移负责人 | — | 全部证据 | 合并/驳回 | 人工门 |

**内置技能包（12 个，与设计稿一致）**：`vue3-analyze`、`vue3-deps`、`vue3-transform`、`vue3-quality`、`vue3-verify`、`vue3-fix`（前序已落地 7 个）+ `vue3-router4`、`vue3-antdv`、`vue3-vite`、`vue3-less`、`vuex-to-pinia`、`experience-distill`。

## 附录 B：内置专家模板（提示词骨架）

1. **结构分析专家**：扫描目录/依赖/技术栈，输出文件清单、迁移点、风险与批次建议；不改代码。
2. **依赖分析专家**：计算依赖图与拓扑序，产出 pinia/vue-router/vite/antdv/less 版本矩阵与升级步骤。
3. **代码转化专家**：按切片做最小语义等价改造（`<script setup>`、Composition API、filters→函数、mixin→composable、`this.$xxx` 归一化）。
4. **质量分析专家**：执行评分流水线，给出分项证据与低分原因，不修改代码。
5. **浏览器验证专家**：启动 dev server，按路由清单验证渲染/交互/控制台，产出截图与失败复现步骤。
6. **修复专家**：针对低分/失败证据做定点修复，控制改动面，沉淀经验。
7. **记忆归纳专家**：把本轮踩坑提炼为可复用经验卡（坑类型/触发条件/解法/适用版本），去重合并、命中计数。
8. **Pinia 迁移专家**：处理 Vuex→Pinia 的 store 拆分、持久化插件、模块命名空间与 devtools 迁移。

> 共 8 张内置专家卡（与设计稿"8 registered / 8 张卡"一致）；**主协调者（Lead）由编排层承担**，不作为专家卡。用户可新增/克隆专家。

## 附录 C：异常分类表（实现口径）

见 §10 与 `research/hermes-capabilities.md` 第 7 节（Hermes 原生错误类型映射）；插件统一错误码 `FLOW_RATE_LIMIT / FLOW_TRUNCATED / FLOW_TIMEOUT / FLOW_PROCESS_INTERRUPT / FLOW_DEP_MISSING / FLOW_BUILD_FAILED / FLOW_LOW_SCORE / FLOW_AGENT_DRIFT / FLOW_QUOTA_EXHAUSTED / FLOW_DAG_INVALID / FLOW_CONFLICT / FLOW_INTERNAL`，批次新增 `FLOW_BATCH_OVERFLOW（上下文/结果超限）/ FLOW_BATCH_SPLIT_LIMIT / FLOW_BATCH_LEASE_LOST / FLOW_BATCH_DUPLICATE / FLOW_BATCH_WRITE_SCOPE（越界写）/ FLOW_BATCH_RESULT_INVALID（JSON 校验失败）`。

## 附录 D：与前序 PRD v1.0 的差异

| 维度 | v1.0（2026-10-17） | v2.2（本文件） |
|---|---|---|
| 定位 | Vue3 迁移专用插件 | 通用控制面 + Vue3 领域包 |
| Agent/Skill | 概念描述，无注册中心 | 一级公民 Registry + UI + 自动加载 |
| UI | 单文件 mockup（7 屏） | Dashboard 原生 tab + 8 屏高保真 + 设计规范 + 截图 + 还原提示词 |
| 自治循环 | 伪代码为主 | 子代理生命周期 + turn 预算 + cron 心跳 + 租约/心跳 |
| 可行性 | 概要 | 逐条证据 + 源码 file:line + 运行时风险 |
| 复用 | 未明确 | 明确复用前序内核/技能/样例，给出迁移路径；纠正 LoopX 虚构布局与错误安装方式 |

---

## 附录 E：Hermes 原生能力 → 插件实现证据索引

| PRD 能力 | Hermes 原生机制 | 源码/文档证据（本机 v0.22.2） |
|---|---|---|
| 插件装载 / register(ctx) | `PluginContext`、`PluginManager.discover_and_load` | `hermes_cli/plugins.py:230,1279`；`website/docs/developer-guide/plugins/index.md` |
| 工具注册 | `ctx.register_tool(name, toolset, schema, handler, ...)` | `hermes_cli/plugins.py:456` |
| CLI / slash / 审批 | `register_cli_command` / `register_command` / `register_approval_transport` | `plugins.py:633,647,430` |
| Hooks / middleware | `register_hook`（`pre_tool_call`/`post_tool_call`/`subagent_stop`/`pre_verify`/`pre_llm_call`…）；`register_middleware` | `plugins.py:933,937,109-204` |
| 子代理 | `ctx.subagent_lifecycle.launch/wait/status/steer/cancel/result/reconnect` | `plugins.py:386`；`developer-guide/subagent-lifecycle-api.md:15-49` |
| 委派 | `delegate_task`（goal/context/output_schema/tasks；无 skills 参数） | `website/docs/user-guide/features/delegation.md:329-342` |
| 技能注册（插件内置） | `ctx.register_skill(name, path, description, frontmatter)` → `plugin:skill` 只读命名空间 | `hermes_cli/plugins_content.py:22-52` |
| 用户技能 | `$HERMES_HOME/skills/<name>/SKILL.md`（原生发现；项目级需 trust） | `features/skills.md:406-428,467-519` |
| Dashboard UI | `dashboard/manifest.json` + 预构建 `dist/index.js`（IIFE，`window.__HERMES_PLUGIN_SDK__`）+ `plugin_api.py`（FastAPI `router` → `/api/plugins/<name>/`） | `features/extending-the-dashboard.md`；先例 `plugins/kanban/dashboard/` |
| 持久状态 | `ctx.state`（JSON ≤10 MiB）、`plugin_data_dir()`、`plugin_db()`（SQLite WAL） | `plugins.py:282`；`plugins/plugin_storage.py` |
| 结构化 LLM | `ctx.llm.complete / complete_structured` | `plugins.py:376`；`developer-guide/plugin-llm-access.md` |
| 异常分类 / 退避 | `FailoverReason` 29 种；`Retry-After` / jitter / adaptive | `agent/error_classifier.py:34-66`；`agent/retry_utils.py:30,121,155` |
| 文件级回滚 | 影子 git checkpoint + `/rollback`（默认关闭） | `website/docs/user-guide/checkpoints-and-rollback.md:10-57` |
| 会话恢复 | `--resume` / `/resume`；goal/loop 状态在 `SessionDB.state_meta` | `website/docs/user-guide/sessions.md:108-185`；`features/goals.md:217-223` |
| 自续跑 `/goal` | aux judge + 确定性 shell 质量门 + `max_turns` | `website/docs/user-guide/features/goals.md:7-9,136-154` |
| 验证 | `pre_verify` hook；`hermes verify` recipe；browser/CDP | `features/hooks.md:823-848`；`hermes_cli/subcommands/verify.py:19-45` |
| 记忆 | `memories/MEMORY.md`（2,200 字符）/ `USER.md`（1,375 字符）；FTS5 `session_search`；memory provider 单例 | `features/memory.md:11-20,235-260`；`developer-guide/memory-provider-plugin.md` |
| 经验召回注入 | `pre_llm_call` 返回 `{"context": ...}`（≤10k 字符） | `plugins/index.md:1300-1339`；`plugins.py:109-204` |
| 定时 | cron（gateway ticker + jobs JSON） | `developer-guide/architecture.md:165-174` |

> 完整逐项证据见 `research/hermes-capabilities.md`（466 行，含所有 file:line）。

## 附录 F：LoopX 关键事实与纠偏

| 维度 | 事实（核验 2026-10-18，HEAD `105c4bc`） |
|---|---|
| 定位 | 长周期 Agent 控制面（不是 Agent 框架/runtime） |
| 仓库 | `loopx-project/loopx`，6,355★ / 604 fork / Apache-2.0（v0.4.8 起）/ 创建 2026-05-31 |
| 形态 | Python CLI 壳 + TypeScript 控制面；`dependencies=[]`，但硬需 **Node ≥ 22.22.3**；主干 `2.0.0a1`，发布线 1.x |
| 稳定契约 | **CLI + JSON**（官方明示）；Python 内核被其架构测试禁止外部 import |
| 真实状态布局 | `<project>/.loopx/registry.json` + `<project>/.loopx/goals/<goal>/ACTIVE_GOAL_STATE.md`；机器级 `~/.loopx/registry.global.json` |
| 生命周期动作 | `quota should-run` / `todo claim` / `todo update|complete` / `refresh-state` / `quota spend-slot`（每 turn 最多一次；receipt 幂等） |
| 官方 DSH 插件 | `packages/dsh-loopx-plugin`，绑定 DSH Loader/GoalBar，**Hermes 不可复用**；`dsh plugin add github:loopx-project/loopx` 被官方否掉 |
| 前序虚构 | ❌ `.loopx/domain-state/*.jsonl` 账本不存在；❌ JSONL 事件溯源已被 PR #5054 退休；❌ "五原语"不是 LoopX 术语 |
| 推荐集成 | **C 混合**：默认自研内核（语义对齐）+ `--backend loopx` CLI 子进程桥接 + `loopx doctor` 探测 + 失败降级 + 单写者 |

> 完整分析（含 CLI 参数、状态机、数据映射、风险与引用 URL）见 `research/loopx-analysis.md`。

## 附录 G：批量循环设计摘要（FR-10）

**一句话**：批次是治理单元，文件是幂等单元；插件循环批次（L1），子代理循环批内文件（L3），同层可并行（L2）。

### G.1 批次 DSL
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

### G.2 执行通道选择
| 场景 | 通道 |
|---|---|
| 插件自治批量循环（默认） | `ctx.subagent_lifecycle.launch/wait`（8 线程池，逐批 model/toolsets；无 output_schema） |
| 同层并行 / 主 Agent 汇总 | `delegate_task(tasks=[≤max_concurrent])`（默认 10；超限报错，需切波；原生 output_schema，summary 24k） |
| 超大规模/跨会话（P2） | kanban dispatcher（每批一卡，gateway 60s tick） |
| 单批文件极多且同质（P2 实验） | `persistent_child`（≤3 批/child，每批 checkpoint；默认关闭） |

### G.3 关键默认值
| 参数 | 默认 | 说明 |
|---|---|---|
| 每批文件数 | 7（自适应 1–12） | 按 28k 字符预算装箱；7 为示例上限参考 |
| 并发批次 | 1 | 仅同 wave 可升到 2–3；并行需 worktree 隔离 |
| 每 tick 批数 | 10 | 同时受 tick_budget_seconds=600 约束；到点保留 handle/checkpoint 退出 |
| 单批等待 | 1800s 累计 | 单次 wait 分片 ≤60s；超时 cancel + 重试/拆批 |
| 重试/拆分 | 3 次 / 2 层 | 超过转人工门 |
| 子代理迭代预算 | 60 | 通过 `delegation.max_iterations` 设置 |
| 结果上限 | lifecycle 32k / delegate 24k | 批次结果按 24k 设计 |
| Run 总预算 | 项目配置 | token/时长超支 → 暂停 + 人工门 |

### G.4 Hermes 证据
| 声明 | 证据 |
|---|---|
| `delegate_task(tasks=[...])` 批量、默认 10 并发、超限报错 | `tools/delegate_tool_config.py:17`；`tools/delegate_tool.py:483-513,543`；`tools/delegate_tool_tasks.py:83`；`delegation.md:211-215` |
| 批量 = 一个 async unit；结果按输入顺序；完成事件持久化但不恢复 child | `delegation.md:184-233` |
| child 迭代上限 250（全局）；默认无 wall-clock 超时；停滞 450s/1200s | `delegation.md:342-380`；`delegate_tool.py:105,111-112`；`delegate_tool_config.py:24-27` |
| leaf 禁止再委派；orchestrator 受 `max_spawn_depth`（默认 1） | `delegation.md:329-342`；`delegate_tool_config.py:21,151-167` |
| `delegate_task` summary 上限 24,000 | `tools/delegate_tool_results.py:160,163,166,275-277` |
| `ctx.subagent_lifecycle` 字段/上限、timeout 被拒、无 output_schema、并发 8、进程内 1h | `agent/subagent_lifecycle.py:25-28,120,159-160,228,277-280,371-375`；`developer-guide/subagent-lifecycle-api.md:15-64` |
| `dispatch_tool` 在 gateway 下 parent_agent 可能为 None | `hermes_cli/plugins.py:674-683` |
| 前序拓扑排序可复用 | `E:\DHLocal\HERMES\vue3migrate-core\vue3migrate_core\migrator.py:134` |

> 完整调研（方案对比 A–E、批规划算法、状态机、失败矩阵、UI 增量、B1–B17 验收）见 `research/batch-loop-analysis.md`。
