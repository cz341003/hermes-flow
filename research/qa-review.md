# HERMES Flow 交付物独立评审报告（QA Review）

> **评审角色**：质量门控 / 独立评审（挑剔的 CTO + 技术评审人视角）
> **评审对象**：`docs/FEASIBILITY.md`（245 行）、`docs/PRD.md`（v2.1，1135 行）、`research/hermes-capabilities.md`（466 行）、`research/loopx-analysis.md`（440 行）、`ui-design/index.html`（293,439 B / 8 屏，13:15:09 版）、`ui-design/screenshots/*.png`（**9 张**：00 总览 + 01–08，13:15:05–16:05）、`ui-design/design-spec.md`（21,877 B）、`ui-design/PROMPTS.md`（24,075 B）、`ui-design/overview.html`、`ui-design/screenshot.ps1`
> **核验基准**：本机 Hermes Agent **v0.22.2**（`E:\hermes\hermes-agent`，`install-stamp.json` commit `d923a5eb…`）；LoopX 以 `research/loopx-analysis.md` 所载 HEAD `105c4bc` 与官方原文为准
> **评审方法**：只读抽查源码/官方文档 **50 处** `文件:行号`；逐条比对 PRD↔FEASIBILITY↔研究文档↔UI 四件套；`index.html` 静态审计（外链/结构/JS 语法/交互代码/DOM 完整性）；`read_image` 逐张检查 9 张截图，对关键区域做局部放大与像素抽样复核
> **评审时间**：2026-10-18 13:00–13:17（Asia/Hong_Kong）；UI 文件在评审期间仍在更新（13:11 → 13:15 → 13:16），**本报告以 13:17 文件状态为准**
> **声明**：本报告不修改任何交付物；未验证项均标"待确认"，不编造。

---

## 0. 总评

**结论：有条件通过（Conditional Pass）**——方案与证据基础成立、交付物已齐全，但**必须先修正 3 类与宿主源码冲突的事实、1 个执行契约缺口、UI/规范/PRD 之间的口径与 tokens 冲突**，再进入实现阶段。

**一句话理由**：Hermes 能力证据的 50 处抽查绝大多数准确（插件 API、技能、持久化、子代理、hooks 全部对得上源码），LoopX 事实与纠偏站得住；9 张截图 + 交互原型 + 设计规范 + 还原提示词的质量明显高于一般交付；但 PRD 有 3 处与 v0.22.2 源码直接冲突的关键事实（路由"必须重启"、SSE 鉴权、`/goal --gate` 语法）、自治闭环缺少可执行的 turn 驱动契约，且 UI 的权重/门控/内核口径与 PRD 相反、设计规范 §8 的集成方案（dsh-plugin/iframe/Vue3-Pinia）与 Hermes Dashboard SDK 不匹配——这些会直接导致实现返工与验收争议。

**问题统计**：**P0 = 0**｜**P1 = 13**｜**P2 = 27**。
（评审早期发现的两项交付缺陷已在 UI 方 13:15–13:16 重渲/补交后关闭：① `04-skills.png` 表格近透明不可读；② `design-spec.md`/`PROMPTS.md` 未交付。详见 §1 复核记录与 §6。）

| 维度 | 判定 | 说明 |
|---|---|---|
| Hermes 事实一致性 | ⚠️ 基本可信 | 抽查 50 条，准确率高；3 条关键机制描述与 v0.22.2 源码冲突（P1-1/2/3） |
| LoopX 事实与纠偏 | ✅ 通过 | 6,355★/604 fork/Apache-2.0/Node 22.22.3/2.0.0a1/CLI+JSON 契约均与 research 一致；前序两处虚构已纠正 |
| 可实现性 | ⚠️ 有缺口 | 8 项需求均有路径；但"谁执行 turn"、SSE 鉴权、LoopX checkpoint 协议三处需要重设计（P1-2/4/7） |
| 需求覆盖 | ⚠️ 基本覆盖 | 8 项需求 FR/UI/验收大体对应；UI 缺历史回放/校准/晋升等 §13.3 验收级元素（P1-5、P2） |
| UI 设计质量 | ✅ 良好 | 8 屏齐全、完全离线、JS 语法通过、导航/抽屉/命令面板/DAG 选中/状态按钮真实可用；9 张截图均可读；但数据口径与 PRD 冲突（P1-5/6/13） |
| 文档质量 | ⚠️ 需修 | 代码围栏不平衡（会吞后文）、v2.1/v2.0 混用、断链 1 处（`research/loopx/`）、若干 typo |
| 计划与验收 | ❌ 偏乐观 | 15–20 人日明显低估；FR-7/G6/SLO 存在不可测条款 |

---

## 1. 阻塞级问题（P0，必须改）

**P0 = 0。** 截至 13:17 复检，未发现必须阻断交付的问题。以下两项在评审过程中曾按 P0 记录，已由 UI 方修复，保留复核记录：

- **已关闭 P0**：`ui-design/design-spec.md`、`ui-design/PROMPTS.md` 曾缺失（13:12 复检为空，PRD:6/756/1088、FEASIBILITY:244、overview.html:34 断链）；13:15:43 / 13:16:14 已补交，现均已存在且内容完整。
- **已关闭 P0**：`04-skills.png` 曾于 13:12 版本渲染为骨架态（技能表 9 行近透明不可读）；13:15 重渲后已正常（279,808 B，表格 9 行完整可读）。根因是 `index.html:259-260` 的 `.page.active{animation:pageIn .28s both}` 与截屏时序竞争，`screenshot.ps1` 现已可稳定复现。
- **待 Lead 决策的收尾项**：UI 文件在评审期间仍在更新（index.html 13:15:09、PROMPTS.md 13:16:14），交付前需**冻结版本**并保证 `index.html / screenshots / design-spec / PROMPTS` 四件套同源（见 §7 Gate 1）。

---

## 2. 重要问题（P1）

### P1-1　"Dashboard 插件后端路由必须重启才挂载"与 v0.22.2 源码冲突（事实错误）
- **文档声明**：`PRD.md:114`、`PRD.md:922`、`PRD.md:1035`；`FEASIBILITY.md:109`；`research/hermes-capabilities.md:145,451` 均称"路由在 web server 启动时挂载，新增/修改后需重启"。
- **源码事实**：v0.22.2 已内置 **hot-mount fallback**：`hermes_cli/web_server_dashboard.py:899-927`（`_try_hot_mount_plugin_api`，首次请求时 force_rescan 后现场挂载）、`:942-963`（`_PluginApiHotMount` ASGI fallback）、`:966-973`（注册 `/api/plugins/{name}/{path:path}` 兜底）。即：**新安装/新启用的插件在首次 API 请求时即可热挂载**；只有"已挂载路由的模块代码变更"才需重启。
- **影响**：① M0 验收步骤与"未挂载引导"逻辑失真；② 风险表（`PRD.md:1035`）与运维约束（`PRD.md:922`）需要改写；③ 官方文档 `extending-the-dashboard.md:916` 仍是旧说法（B 级证据），本报告按"源码优先"判定。
- **修法**：改为"新增/启用插件由首次请求热挂载；修改已挂载的 `plugin_api.py` 需重启；`/api/dashboard/plugins/rescan` 只重扫前端 manifest"。

### P1-2　"SSE 事件流"按现状写法无法通过 Dashboard 鉴权（方案不可直接用）
- **文档声明**：`PRD.md:204,373,795,915` —— Dashboard 通过 `SSE /api/plugins/hermes_flow/events?run_id=` 订阅，断线从 `Last-Event-ID` 续传。
- **源码事实**：Dashboard 的 `/api/*`（含 `/api/plugins/*`，不在公开白名单）要求 `X-Hermes-Session-Token` 或 `Authorization: Bearer`（`hermes_cli/web_server.py:476-516`、`:721-739`）；`?token=` 仅对 `/api/files/download` 白名单开放（`:490-499`）。浏览器原生 `EventSource` **不能设置自定义请求头**。
- **先例**：kanban 的实时流用 **WebSocket**，凭证走 query string：`plugins/kanban/dashboard/plugin_api.py:50（_ws_upgrade_authorized）、:1802（@router.websocket("/events")）`。
- **影响**：PRD 的 SSE 方案照字面实现会在浏览器端 401。
- **修法（择一）**：① 改用 WebSocket（复用 kanban 的 `?token=/?ticket=` 鉴权模式）；② 保留 SSE 但用 `fetch` 读 `ReadableStream`（可带 `X-Hermes-Session-Token`），自行实现 `Last-Event-ID`；③ 前端用 `SDK.fetchJSON` 1s 轮询（能过 P95≤1s？需重估）。PRD、API 表与测试矩阵需同步。

### P1-3　`/goal --gate "..."` 语法在 v0.22.2 不存在（驱动方案写错）
- **文档声明**：`PRD.md:660` 写 `/goal <完成目标> --gate "hermes flow status --run <id> --json 判 done"`。
- **源码事实**：`/goal` 的 gate 通过子命令管理：`/goal gate add <command>`、`gate list/remove/clear`（`hermes_cli/goal_command.py:81-134`、`:209`；`website/docs/user-guide/features/goals.md:70-73`），**没有 `--gate` 参数**。
- **追加缺陷**：gate 的语义是"shell 命令 exit 0 才允许 judge 判 done"（`goals.md:138-150`），而 `hermes flow status --json` 正常返回也是 exit 0 → 需要"未完成即非零退出"的命令约定（PRD 未定义）。
- **修法**：改成 `/goal gate add hermes flow gate --run <id>`（该命令仅在 Run 成功时 exit 0），或在 M0 定义 `flow status --strict` 契约；PRD §10.4 表格与 §16.4 演练脚本同步。

### P1-4　自治闭环缺少"谁执行 turn"的可实现契约（前台驱动不可行）
- **源码事实**：`ctx.subagent_lifecycle.launch()` 必须存在**活跃父会话**，否则抛 `SubagentLifecycleError("No active Hermes parent session is available.")`（`agent/subagent_lifecycle.py:277-280`）；且 children **只在进程内运行**、进程退出后 `reconnect` 返回 `RECONNECT_UNAVAILABLE`（`:270-272`、`:371-375`）。`ctx.dispatch_tool` 在 web server 中 `_cli_ref.agent` 为 None（`hermes_cli/plugins.py:674-684`）。
- **文档缺口**：`PRD.md:661` 的第三种 driver 写"用户打开 Dashboard/会话，`flow_tick` 手动或**前端心跳驱动**"；`PRD.md:922` 的 API 只创建 Run；全文没有定义"Dashboard 点击开始后由哪个 agent turn 去 launch 子代理"。
- **影响**：若按字面在 `plugin_api.py` 的 REST handler 里推进 run，会在 launch 处失败。cron（gateway 内嵌 ticker，`architecture.md:165-174`）与 `/goal` 两种 driver 可行，但 PRD 未把"cron job 由谁创建/如何常驻"写成可执行步骤。
- **修法**：明确 tick 只能由 agent turn 触发（cron prompt → agent 调 `flow_next_turn`；或 `/goal` gate + 工具；或聊天会话内工具），Dashboard 的"开始/继续"只做"建 Run + 创建/唤醒 cron heartbeat + `ctx.inject_message` 通知"，**不得**在 REST handler 直接 launch；并在 §16.1 增加"无活跃会话时 Run 停在 queued，前端显示下一步引导"的验收。

### P1-5　UI / design-spec / PROMPTS 与 PRD 的口径系统性冲突（权重/门控/并发/计数）
| 项 | PRD | UI 四件套（index.html / design-spec / PROMPTS / 截图） | 判定 |
|---|---|---|---|
| 五信号权重 | 20/25/15/25/15（`PRD.md:465-469`，DSL `PRD.md:540` 同） | 25/20/20/15/20（`index.html:1965,3174,3321`；`design-spec.md:166`；`PROMPTS.md:76,285`；截图 01/07/08） | ❌ 冲突 |
| 门控语义 | ≥85 通过；70–84 **警告通过**；<70 回环（`PRD.md:471`） | "低于阈值(85)自动回环"（`index.html:3094,3403`）；70–84 分布标注为"回环"（`:3189,3195`） | ❌ 冲突 |
| 硬门规则 | 仅 build 失败 / 浏览器白屏（`PRD.md:472,691`） | 追加"单信号 <60 直接回环"（`:3198,3211`）、"行为一致性下限 80"（`:3212,2545`）；`design-spec.md:159` 描述为"阈值 85 参考环"但未写这两条硬门 | ❌ PRD 未定义 |
| 并发 | 默认 3（`PRD.md:622`、`:1050`） | 并发 4/4（`:1800,1899,2641,2784`；`PROMPTS.md:65,69,93`；截图 01/02/08） | ⚠️ 冲突 |
| 专家名单 | 附录 B 7 位（含主协调者，`PRD.md:1068-1076`） | 8 位且不同（新增"记忆归纳/Pinia 迁移"，无主协调者；`index.html:1980,2184`；`design-spec.md:131-132`；截图 03） | ⚠️ 不一致 |
| 技能数 | 附录 A 约 10 个（7 内置 + 3 补充，`PRD.md:963`） | 12 个且名称不同（`index.html:2184`；`design-spec.md:33,138`）；筛选 5+3+1+1+1=11 ≠ 12（P2-27） | ⚠️ 不一致 |
- **影响**：FR-7 验收"对样例项目评分与预期一致"（`PRD.md:490`）无法成立；实现方会照 UI 或照 PRD 各写一套；`screenshot.ps1` 已把错误口径固化成回归基线。
- **修法**：以 PRD 权重为准改 UI；把 UI 新增的硬门规则要么写入 PRD 门控规则与数据模型，要么从 UI 删除；统一并发/专家/技能演示数据；**修订时 PRD、design-spec、PROMPTS、index.html、截图五处同步**。

### P1-6　UI 默认内核与 PRD 相反，且 LoopX 版本号虚构
- **UI**：侧栏 `LoopX Kernel / CONNECTED / v0.9.2`（`index.html:1680,1688`，9 张截图均可见）；设置页"LoopX Kernel v0.9.2 **默认内核**"（`:3357-3360`）、自研"Hermes Kernel v0.6 beta … **暂不支持断点续跑**"（`:3364`）；命令面板 toast"当前生产内核"（`:4312`）；`design-spec.md:166,227`、`PROMPTS.md:32,303-305` 同样把 LoopX 写为默认。
- **PRD**：默认自研 SQLite 内核、LoopX 为 `--backend loopx` 可选（`PRD.md:130,500-502`、FR-8）；自研内核本就要支持 checkpoint/续跑（FR-6）。
- **LoopX 真实版本**：发布线 1.x、主干 `2.0.0a1`（`research/loopx-analysis.md:41`、`PRD.md:129`）——**不存在 v0.9.2**。
- **修法**：UI/规范/提示词统一改为默认"自研 SQLite Kernel（已连接）"，LoopX 作为可选/未启用；版本号删除或标注"演示数据"。

### P1-7　FlowKernel 协议包含 `checkpoint/restore`，LoopX CLI 无对应能力
- **文档**：`PRD.md:500` 定义 `FlowKernel` 协议 = `should_run / claim / update / refresh_state / spend_slot / checkpoint / restore`；`LoopXKernel` 只通过 CLI 调用。
- **研究结论**：LoopX 侧 Checkpoint "**不是独立存储**：是 checkpointed boundary authority + vision checkpoint"（`research/loopx-analysis.md:339`），没有 checkpoint/restore CLI。
- **影响**：`LoopXKernel` 无法实现协议，FR-8 验收"两内核状态一致"必然失败或被迫双写。
- **修法**：把 checkpoint/restore 从内核协议上移到"编排层本地 JSON checkpoint"（两内核共用），或为 LoopX 后端定义为 no-op + 本地快照；PRD §14.6/FR-8 同步。

### P1-8　"5 项原生 + 3 项自研"与 FEASIBILITY"5 项需自建"自相矛盾
- **PRD**：`PRD.md:91` "5 项 Hermes 原生已具备基础能力，3 项需要插件自研"。
- **FEASIBILITY**：`FEASIBILITY.md:16` 列"需要插件自研：①专家注册表 ②DAG ③评分卡 ④经验库 ⑤控制面 UI"；`FEASIBILITY.md:171` "共 5 项需自建"。
- **PRD 自身**：§3.1 表中 req1/3/6/7/8 均写"插件补/自研"，与"3 项"也对不上。
- **修法**：统一为"5 项需求需插件补足能力（专家注册表/DAG/质量卡/经验库/控制面 UI），其余复用"，并让表格口径一致。

### P1-9　设计稿/规范与 Hermes Dashboard 集成方式冲突（自建壳 + 错误技术栈 + 错误宿主术语）
- **设计稿**：`index.html:1627-1700` 自建 `<aside class="side">`（HERMES 品牌、8 项主导航、内核卡）+ `:1695` 自建 topbar（面包屑/搜索/目标 chip/通知/头像/命令面板）——是**完整应用壳**，9 张截图均是整屏独立应用。
- **PRD**：`PRD.md:793-794` 明确 `/flow` 一个 tab + "UI 使用 Dashboard 暴露的 Plugin SDK…**不自建壳**、不 fork Dashboard"。
- **design-spec §8 错误**（`design-spec.md:215-242`）：推荐"dsh-plugin 的 dashboard 以子路由 `/hermes` 挂载"、iframe + `postMessage({type:'host:theme'})`、`vue-router` hash + Pinia + SSE/WebSocket。**Hermes 不是 dsh-plugin**；Hermes Web Dashboard 插件契约是 `dashboard/manifest.json` + 预构建 IIFE `dist/index.js` + `window.__HERMES_PLUGIN_SDK__`（React 由宿主提供）+ `plugin_api.py` router（见 §4 证据 #16/#17/#20），**不是 iframe/子路由/Vue 技术栈**。
- **PROMPTS §0 同样错误**（`PROMPTS.md:5`）："若用 Vue3，把结构映射为 SFC 即可"。
- **影响**：若照 design-spec/PROMPTS 实现，会得到一个无法挂进 Hermes Dashboard 的独立 Vue 应用；返工量与视觉重做成本高。
- **修法**：design-spec §8 重写为 Hermes 插件 SDK 方案（React 组件 + `register()` + `registerSlot()`；或明确"若坚持独立壳，则 PRD 改为独立部署形态并放弃 Dashboard tab"）；PROMPTS 的技术栈说明同步；PRD §13.4 增加"落地为 tab 内子导航、复用宿主侧栏/顶栏"的映射说明。

### P1-10　工作量与里程碑明显偏乐观
- **数字**：MVP 15–20 人日（`FEASIBILITY.md:30,221`、`PRD.md:970`）；M2 5–7 天完成 DAG DSL+调度器+状态机+租约/心跳+Run API+SSE+编排/监控两屏（`PRD.md:976`）；阶段 A 10–12 人日覆盖专家/技能+DAG+8 屏+质量门+异常恢复+E2E（`FEASIBILITY.md:229`）。
- **对比交付面**：8 屏高保真（本设计稿已是 293 KB 单文件 + 21 KB 规范 + 24 KB 提示词）、20+ 工具、SQLite 内核、五信号评分（AST/构建/类型/浏览器/行为）、SSE/WS、租约/心跳、经验库 FTS5、LoopX CLI 桥接、E2E 故障演练。
- **判定**：**不现实**。建议 30–45 人日（UI 5–8、引擎 6–8、评分/证据 6–8、恢复/租约 4–6、记忆 3–4、桥接 4–6、测试/文档 5–8），并拆出"可演示 MVP（假数据 UI + 单链路引擎）"。
- **修法**：重排里程碑与人力；把 M2 拆为 M2a（引擎）/M2b（SSE+两屏）。

### P1-11　关键验收条款不可测
- `PRD.md:490` FR-7 验收："对样例项目评分与预期一致"——**没有提供任何预期分数/基线表**（FEASIBILITY 自己也承认"评测先行、先定义评分基线"，`FEASIBILITY.md:232`）。
- `PRD.md:71` G6："重复坑位二次出现率**显著下降**"——无样本量、对照口径、显著性定义。
- `PRD.md:1004` SLO："断点续跑成功率 ≥99%（模拟 20 次中断）"——20 次试验无法支撑 99%（20/20 成功时 95% 置信下界约 83%）。
- `PRD.md:380` "两个浏览器同时打开看到一致状态"——未定义判定方法（快照 diff？事件序列比对？）。
- **修法**：给出样例项目 20 文件的**预期分数表与允许误差**、经验命中的 A/B 口径与样本量、以及可执行的 SLO 统计方法（如 100 次中断 + 允许 1 次失败）。

### P1-12　`skills.write_approval` 门控叙述不准确（安全叙事）
- **文档**：`PRD.md:110,315` 称用户技能写入"受 `skills.write_approval` 门控"。
- **源码/文档**：该门控只作用于 **`skill_manage` 工具**的写入（create/edit/patch/delete/write_file/remove_file，统一 staged 审批，见 `website/docs/user-guide/features/skills.md:668-700`）；插件直接 `write_text` 到 `~/.hermes/skills/` **不经过该门控**。
- **修法**：二选一并写进 FR-2：① 通过 `ctx.dispatch_tool("skill_manage", …)` 走门控（需在 agent turn 内）；② 直接写文件，则删除"受门控"表述，并声明插件自身做校验/备份。

### P1-13　三套视觉 tokens 互相不一致（PRD / design-spec / index.html），且 a11y 声明基于不存在的值
- **PRD §13.2**（`PRD.md:775-777`）：底 `#0B0F17`、面板 `#121826`、主色 `#38BDF8`、运行 `#3B82F6`、通过 `#22C55E`、警告 `#F59E0B`、失败 `#EF4444`、回环 `#A855F7`、人工门 `#F97316`；导航 **240px**；内容最大宽 **1600px**；卡片圆角 **12px**。
- **design-spec §3.1/§3.3**（`design-spec.md:55-68,100`）：底 `#07090B`、面板 `#0F1419`、主色 `#35CFC1`、通过 `#56C98A`、警告 `#E0A93E`、失败 `#E9695F`；导航 **236px**；内容最大宽 **1680px**；圆角 **3/5/7/9px**。
- **index.html 实际**（`index.html:16-45`）：`--bg #07090B`、`--acc #35CFC1`、`--ok #56C98A`、`--warn #E0A93E`、`--err #E9695F`、`--side-w 236px`、`--r-* 3/5/7/9px` —— 与 design-spec 一致，与 PRD §13.2 **完全不同**。
- **design-spec 内部又错**：§3.1 写 `--ink-2 #A9B5C1`、`--ink-3 #8B97A4`、`--ink-4 #5D6976`，`index.html:27-30` 实际为 `#A3AFBB`、`#737F8C`、`#4C5865`；§7 的对比度结论（如 `#8B97A4` 5.4:1）因此不成立（P2-26）。
- **影响**：三方任选其一实现都会与另两份冲突；a11y 验收无法判定。
- **修法**：以 `index.html` + design-spec 为事实源回写 PRD §13.2（这是设计稿落地后的正常反向同步）；design-spec 的 ink token 与对比度按实际值重算；把 tokens 抽成单一来源（PRD 引用 design-spec，而不是各自维护）。

---

## 3. 建议改进（P2）

1. **FailoverReason 数量**：`PRD.md:100`、`FEASIBILITY.md:79`、`hermes-capabilities.md:23,305` 写"30+"；源码 `agent/error_classifier.py:34-66` 实际 **29** 个成员（含 `unknown`）。改为"29 种（30+ 语义类别）"。
2. **`ctx.subagent_lifecycle` 能力描述不准确**：`PRD.md:293` "只接受 goal/context/model/toolsets"；实际还接受 `role/provider/blocked_tools/working_directory/parent_session_id/correlation_id/metadata`（`agent/subagent_lifecycle.py:48-62`），且 **`timeout_seconds` 明确不支持**（`:228`）——节点超时必须由插件自管，建议写出。
3. **"插件 API 无全局版本号"**（`PRD.md:128,1033`）与 `plugin.yaml:api_version`（`plugins_manifest.py:372-375`）字段存在不符；建议改为"有 `api_version` 但不做强制兼容承诺，仍需锁 `requires_hermes` + CI 回归"。
4. **Turn Packet 32KB 单位**（`PRD.md:617`）：子代理 `context` 上限是 **32,000 字符**（`subagent_lifecycle.py:223-224`），PRD 写 32KB（字节）在纯 ASCII 场景会超限；建议统一为"≤32,000 字符，且中文按字符计"。
5. **FR-8 版本策略自相矛盾**（`PRD.md:503`）："pin 精确版本（建议 `loopx==1.2.x` 起）"——pin 与范围矛盾；dsh 插件下限实为 **≥1.2.4**（`research/loopx-analysis.md:41,383`）。建议 `loopx==1.2.4` 或 `>=1.2.4,<1.3`。
6. **LoopX 桥接缺少 Node PATH 缓解**：`research/loopx-analysis.md:370` 建议"把 Hermes 自带 node 目录注入子进程 PATH"，PRD FR-8（`:501-502`）未写；Hermes `tools\node-26.7.0` 不一定在 PATH。
7. **cron driver 前置条件**：`PRD.md:659` 称 cron"进程独立于对话、最稳"——实际 cron 由 **gateway 内嵌 ticker** 驱动（`architecture.md:165-174`；PRD 自己在 `:1117` 也写"gateway ticker"）。gateway 未运行则无 tick，建议在 §10.4 写明前置条件。
8. **SQL claim 条件 NULL 缺陷**（`PRD.md:955`）：`WHERE status='ready' AND lease_expires_at < now` 对新行（`lease_expires_at` 为 NULL）恒为 NULL/假，永远 claim 不到；应改为 `(lease_expires_at IS NULL OR lease_expires_at < :now)`。
9. **UI 百分比自相矛盾**：`index.html:3111` 显示"91.3% / 71 / 78"，71/78 = **91.03%**；`:1761`、`design-spec.md:117,158`、`PROMPTS.md:59,266` 与截图 01/07 同。建议统一为 91.0% 或调整计数。
10. **UI 领域数据用了 Element UI**（`index.html:2048,2263-2269,3559,3818`；`design-spec.md` 技能列表；截图 03/04），与 PRD 技术栈 **Ant Design Vue 1.x→4.x**（`PRD.md:24,1062`，技能 `vue3-antdv`）冲突；应替换为 antdv 示例（a-table scopedSlots 等）。
11. **UI 引入 CEL 表达式**（`index.html:2563`；`design-spec.md:147`），PRD 仅说"条件表达式只读白名单变量、避免任意代码执行"（`PRD.md:567`），未提 CEL；需在技术选型中确认或改为自有白名单表达式。
12. **PRD 代码围栏不平衡**：`PRD.md:858` 开、`:880` 闭、**:882 多出一个 ```**（全文 25 个 fence，奇数）。部分 Markdown 渲染器会把 §14.4–§14.6 吞进代码块。删除 `:882`。
13. **版本号混用**：头部 `PRD.md:5` 为 v2.1，正文 `:56,93,130,960,1084` 仍写 v2.0；附录 D 标题"v2.0（本文件）"。统一为 v2.1 或说明"v2.1 为 v2.0 修订"。
14. **typo**：`PRD.md:978` "经验库/偏好、设置在、样例项目 E2E" → "设置页"；`PRD.md:970` 标题"4 个迭代"与 M0–M5 五个里程碑不符。
15. **断链**：`research/loopx-analysis.md:6` 称产出含 `E:\deepSeek\research\loopx\`，实际该目录不存在（clone 失败）。建议改为"尝试 clone，失败，故无本地副本"。
16. **UI 交付目录残留**：`ui-design/_src/` 下新增 30 个渲染临时目录（`r-agents/`、`r-flow/`、`shot-*/`、`r2-*/`、`rov3/`、`rs-*/`），整个 `_src` 达 **218 MB**（主要是浏览器 profile 缓存）；建议清理为可复现源码（CSS 4 段/HTML 5 段/JS/构建脚本），并 gitignore 渲染产物。
17. **需求描述 6 条中的"上下文膨胀"无验收**：PRD §1.2 痛点 1（`PRD.md:38`）对应 Turn Packet/切片（§9.2、§8.2.3），但 §16 验收未覆盖"长跑后约束不丢失/上下文不膨胀"的可测项，建议加"单节点输入 ≤32k 字符且 Turn Packet 无全量历史"的断言。
18. **测试矩阵缺口**（`PRD.md:1011-1016`）：缺 LoopX 双内核契约测试的落点、安全（CSRF/同源/插件未启用 404）、Windows 路径/长路径、旧插件 `vue3_migration` 迁移与数据导出、consent/capability 流程、以及"插件禁用后 UI 引导"用例；§16.1 功能验收未覆盖 FR-8/FR-9。
19. **前端工具链来源未说明**（`PRD.md:465-468,812`）：`@vue/compiler-sfc`/`vue-tsc`/`vite` 需目标项目 `node_modules`；Hermes 自带 Node 26.7 未保证在 PATH。建议在 FR-7 写明"探测项目自带工具链→回退 Hermes node→不可用则该信号记 0 并标注"。
20. **插件启用与 consent 未进计划**：Dashboard UI/API 仅在 `plugins.enabled` 白名单且已授权时可用（`web_server_dashboard.py:791-806`；`web_server.py:668-707` 禁用即 404）。M0/M1（`PRD.md:974-975`）未列"enable + capability consent + 热挂载验证"。
21. **两套视觉语言（总览页）**：`overview.html:8-18` 用 PRD 的 `#0B0F17/#38BDF8`，与 `index.html` 和 design-spec 的青绿 `#35CFC1` 不一致；总览图与主体截图的色温不同，建议 overview 也用同一 tokens。
22. **截图仅视口高度**：9 张均为视口截屏（00 为 1600×1060），`08-settings.png` 底部（失败升级人工门/低分优先重排/危险区）被截断；如需完整验收建议补 full-page 或说明。
23. **跨屏数据不一致**：`02-monitor.png` 日志写"工作流校验通过 · **9 节点 / 10 连线**"（`index.html:2780`），而 `05-flow.png` 与 design-spec 为"**8 节点 · 8 连线**"（`design-spec.md:145`）；需统一。
24. **质量页"最近 5 项" vs PRD"低分 Top 10"**（`index.html:3225` vs `PRD.md:788`）；建议统一为 Top 10 或改 PRD。
25. **design-spec §3.1 ink token 与实际不符**（`design-spec.md:62-63` vs `index.html:27-30`）：`#A9B5C1` vs `#A3AFBB`、`#8B97A4` vs `#737F8C`、`#5D6976` vs `#4C5865`；§7 的对比度结论需按实际值重算（例如 `#737F8C` 在 `#0F1419` 上约 4.2:1，达不到其声称的 5.4:1）。
26. **design-spec 阶段筛选计数**：§4-04（`design-spec.md:138`）"全部12 / transform5 / deps3 / quality1 / verify1 / memory1" → 合计 11 ≠ 12；`PROMPTS.md:159` 同。建议补 `build 1` 或改为 11。
27. **design-spec §2 与 §4-03 数据**：§2 写"8 个专家卡片"（`design-spec.md:33`），§4-03 筛选写"运行 2 / 空闲 4 / 失败 1 / 已完成 1"（`:131`），截图 03 一致；但 PRD 附录 B 只有 7 位专家（P1-5 表）——需在 PRD 侧补"记忆归纳/Pinia 迁移"或 UI 侧删两张卡，保持单一事实源。

---

## 4. 事实核验抽查表

> 判定：✅ 与源码/官文一致；⚠️ 部分准确/表述不精确；❌ 与源码冲突或证据缺失。行号均以本机 v0.22.2 源码/文档为准（UTF-8 行号）。

| # | 声明（出处） | 证据（file:line） | 判定 |
|---|---|---|---|
| 1 | `PluginContext` 定义（FEAS:50、CAP:85） | `hermes_cli/plugins.py:230` | ✅ |
| 2 | `register_tool(name, toolset, schema, handler, …)`（PRD:864） | `plugins.py:456-459` | ✅ |
| 3 | `register_cli_command` / `register_command`（PRD:866-867） | `plugins.py:633` / `:647` | ✅ |
| 4 | `VALID_HOOKS` 含 `pre_tool_call/post_tool_call/pre_verify/pre_llm_call/subagent_stop`（PRD:872-876） | `plugins.py:109-204` | ✅ |
| 5 | `register_middleware` kind ∈ tool_request/llm_request/tool_execution/llm_execution（PRD:877） | `plugins.py:937`；`developer-guide/plugins/index.md:1435-1438` | ✅ |
| 6 | `register_skill(name, path, description="", frontmatter=None)` → `plugin:skill` 只读（PRD:870,1105） | `hermes_cli/plugins_content.py:22-52` | ✅ |
| 7 | `plugin_data_dir`/`plugin_db` → `<home>/plugin-data/<name>/`、SQLite WAL（PRD:110,843） | `plugins/plugin_storage.py:27-46` | ✅ |
| 8 | `ctx.state` durable JSON ≤10 MiB（PRD:1108） | `hermes_cli/plugins_state.py:19,134` | ✅ |
| 9 | `ctx.llm.complete_structured` + provider/model 门控（PRD:482,1109） | `agent/plugin_llm.py:427-470`（`_gate`/`_check_overrides`） | ✅ |
| 10 | `ctx.subagent_lifecycle.launch/wait/status/steer/cancel/result/reconnect`（PRD:1103） | `plugins.py:386-391`；`developer-guide/subagent-lifecycle-api.md:15-64` | ✅ |
| 11 | `SubagentLaunchRequest` 支持 goal/context/role/model/allowed_toolsets/correlation_id（FEAS:107、PRD:107） | `agent/subagent_lifecycle.py:48-62` | ✅ |
| 12 | 子代理结果 ≤32k、重启 reconnect 不可用（CAP:236） | `subagent-lifecycle-api.md:54,64`；`subagent_lifecycle.py:371-375` | ✅ |
| 13 | **launch 需要活跃父会话、children 仅进程内**（PRD 未覆盖） | `subagent_lifecycle.py:277-280`、`:269-272` | ⚠️ 见 P1-4 |
| 14 | `timeout_seconds` 不由 launch 支持（PRD 未声明） | `subagent_lifecycle.py:228` | ⚠️ 需写明（P2-2） |
| 15 | `delegate_task` 无 skills 参数（FEAS:117、PRD:293） | `delegation.md:329-342`；CAP:203 | ✅ |
| 16 | Dashboard manifest 字段 name/label/tab{path,position,override,hidden}/slots/entry/css/api（PRD:793、CAP:143） | `web_server_dashboard.py:517-555`；`extending-the-dashboard.md:470-486` | ✅ |
| 17 | `plugin_api.py` 导出模块级 `router`，挂 `/api/plugins/<name>/`（PRD:107,922） | `web_server_dashboard.py:1034-1043`；docs `:728-748,917` | ✅ |
| 18 | **路由只在启动时挂载、需重启**（PRD:114,922,1035） | `web_server_dashboard.py:899-973`（hot-mount）→ 与声明冲突 | ❌ P1-1 |
| 19 | `/api/dashboard/plugins/rescan` 热重扫前端（PRD:114） | `hermes_cli/web_routers/dashboard_ui.py:149`；docs `:819,885` | ✅ |
| 20 | SDK `window.__HERMES_PLUGIN_SDK__`、`window.__HERMES_PLUGINS__.register/registerSlot`、React 由宿主提供（PRD:794、FEAS:125） | `extending-the-dashboard.md:366-417,497-571,893-895` | ✅ |
| 21 | 插件启用白名单 `plugins.enabled`、禁用后 API 404（PRD:922） | `E:\hermes\config.yaml:63-74`；`web_server_dashboard.py:791-806`；`web_server.py:668-707` | ✅ |
| 22 | `requires_hermes` / `capabilities` / `manifest_version` 为合法 manifest 字段（PRD:1033） | `hermes_cli/plugins_manifest.py:33-38,364,370,478-552` | ✅ |
| 23 | manifest v1 永久支持（PRD:128） | `plugins_manifest.py:134`；`plugin_validate.py` | ✅ |
| 24 | "插件 API 无全局版本号"（PRD:128） | 有 `api_version` 字段（`plugins_manifest.py:372-375`） | ⚠️ P2-3 |
| 25 | MEMORY.md 2,200 / USER.md 1,375 字符（PRD:99,1115） | `features/memory.md:11-20` | ✅ |
| 26 | `pre_llm_call` 返回 `{"context":…}`、上限 10,000 字符、超出落 `hook_outputs/`（PRD:112,876） | `developer-guide/plugins/index.md:1300-1339` | ✅ |
| 27 | `/goal` = aux judge + 确定性 shell 门（gate 先于 judge）+ `max_turns=20` + `state_meta` 可 resume（PRD:116,1113） | `features/goals.md:50,119,136-154,195-197,217-223` | ✅ |
| 28 | `/goal --gate "…"` 可直接带 gate（PRD:660） | `goal_command.py:81-134`（只有 `gate add`）；docs `:70-73` | ❌ P1-3 |
| 29 | 30+ `FailoverReason`（PRD:100、FEAS:79） | `agent/error_classifier.py:34-66` → 29 个 | ⚠️ P2-1 |
| 30 | `retry_utils` Retry-After/jitter(base 5s/max 120s/0.5)/adaptive（PRD:425） | `agent/retry_utils.py:30,121,155` | ✅ |
| 31 | 迭代预算 父 500 / 子 250（FEAS:81） | `tools/delegate_tool.py:105`（`DEFAULT_MAX_ITERATIONS=250`）；`agent-loop.md:180-186`（父 500；该文档写子 50 已过时） | ✅（源码） |
| 32 | `pre_verify` 仅在编辑代码后触发、可 continue/block-stop、`max_verify_nudges=3`（PRD:478） | `features/hooks.md:459,823-848,858` | ✅ |
| 33 | `hermes verify` recipe + `--json`（PRD:479） | `hermes_cli/subcommands/verify.py:19-45`；`agent/verify/__init__.py` | ✅ |
| 34 | checkpoints 默认关闭（PRD:427、FEAS:82） | `checkpoints-and-rollback.md:10,92` | ✅ |
| 35 | 技能 trust / project 技能不自动加载（CAP:189、PRD:1106） | `features/skills.md:467-519` | ✅ |
| 36 | `skills.write_approval` 只门控 `skill_manage`（PRD:110 误述为门控所有技能写） | `skills.md:668-700` | ⚠️ P1-12 |
| 37 | browser 10+ 工具 + CDP、computer_use（PRD:481） | `features/browser.md:10-18,72-92`；`computer-use.md` | ✅ |
| 38 | cron 由 gateway 内嵌 ticker 驱动（PRD:659 称进程独立；:1117 已正确） | `architecture.md:165-174`；CAP:255 | ⚠️ P2-7 |
| 39 | profile = 独立 HERMES_HOME（FEAS:57） | `user-guide/profiles.md:403-410` | ✅ |
| 40 | 技能索引快照 `<home>/.skills_prompt_snapshot.json`（CAP:51,196） | `agent/prompt_builder.py:1208-1209,1581` | ✅ |
| 41 | LoopX HEAD `105c4bc`、6,355★/604 fork、Apache-2.0(v0.4.8+)、Node≥22.22.3、2.0.0a1、发布线 1.x（PRD:129,496,1126-1127） | `research/loopx-analysis.md:13,32-41`（GitHub API/raw 原文） | ✅ |
| 42 | `.loopx/domain-state/*.jsonl` 不存在；真实布局 `.loopx/registry.json` + `goals/<goal>/ACTIVE_GOAL_STATE.md`（PRD:131,1129） | `loopx-analysis.md:85-99,279` | ✅ |
| 43 | `dsh plugin add github:loopx-project/loopx` 对 Hermes 无效且被官方否定（PRD:131,1131） | `loopx-analysis.md:23,267,286`；前序 `E:\DHLocal\HERMES\docs\PRD.md:426`、`README.md:304-305` 确有错误 | ✅ |
| 44 | "五原语"不是 LoopX 术语（PRD:499,1132） | `loopx-analysis.md:130` | ✅（但 PRD:13/102/962 仍按 LoopX 术语使用 → 见 P2 一致性） |
| 45 | LoopX Python 内核被架构测试禁止外部 import / CLI+JSON 为稳定契约（PRD:129,1128） | `loopx-analysis.md:16,226` | ✅ |
| 46 | **SSE 可直接由 Dashboard 浏览器订阅**（PRD:373） | `web_server.py:476-516`（需 session token 头）；`?token=` 仅 `/api/files/download`（:490-499） | ❌ P1-2 |
| 47 | 运行时 `tools\python-3.14.7…\python.exe` 被 ACL 拒绝、`hermes.cmd` 硬编码（PRD:120,FEAS:200） | 本机复现：`Test-Path`/`Get-Item` → `Access is denied`；`E:\hermes\bin\hermes.cmd:3` 硬编码该路径；pm-runtime 可执行文件存在 | ✅ |
| 48 | 旧插件 `vue3_migration`：16 工具 + CLI + board_render + 77 KB 经验库（PRD:50,124） | `E:\hermes\plugins\vue3_migration\plugin.yaml`（16 项）、`__init__.py:571-573`、`state/experience.db` 77,824 B | ✅ |
| 49 | 前序内核 123 单测、7 个迁移技能、20 文件样例（PRD:51-53） | `E:\DHLocal\HERMES\vue3migrate-core`（`def test_` = 123 个）、`E:\hermes\skills\migration` 7 个、`sample-app` 20 文件 | ✅ |
| 50 | 证据文档自报行数 466 / 440（FEAS:4、PRD:1119） | `hermes-capabilities.md` 466 行、`loopx-analysis.md` 440 行 | ✅ |

---

## 5. 需求覆盖矩阵

### 5.1 用户 8 项需求 × PRD × UI × 验收

| # | 需求（FEAS/PRD §3.1） | PRD 章节 | 功能要点 | UI 屏 | 验收条款 | 判定 |
|---|---|---|---|---|---|---|
| 1 | 自定义 Agent + 技能并自动加载 | FR-1（`:278-301`）、FR-2（`:303-323`）、§14.2-14.3 | 专家注册表、技能绑定、自动加载、SKILL.md 校验 | 专家（`03-agents.png`）、技能（`04-skills.png`） | FR-1 验收（`:301`）、FR-2 验收（`:323`）、§16.1 | ⚠️ 有卡片/抽屉/筛选/8 专家；但**无"粘贴提示词→3 步向导"**（G1 要求 3 步内生成）；技能详情无 frontmatter 校验预览 |
| 2 | 显示已加载 Agent/技能 | FR-1/FR-2、§6.2、§14.5 | Dashboard tab 展示已加载专家/技能 | 专家、技能 | FR-1/FR-2、§16.1 | ✅ 卡片+表格双视图、绑定 chips、成功率、最近运行均在（截图 03） |
| 3 | 自定义协作流程/工作流 | FR-3（`:325-358`）、§8 | DAG 画布/节点库/属性/校验/模板/版本 | 工作流编排（`05-flow.png`） | FR-3 验收（`:358`） | ⚠️ 三栏、8 节点 8 连线、属性面板齐全；画布为静态 SVG（无拖拽/连线 JS，设计稿可接受）；无"试运行/发布"按钮（PT 仅 保存/运行工作流） |
| 4 | 可视化工作流进度/Agent 状态 | FR-4（`:360-380`）、§9.3 | Goal 卡、DAG 着色、专家矩阵、时间轴、证据抽屉、历史回放 | 工作台（`01`）、运行监控（`02`） | FR-4 验收（`:380`） | ⚠️ 实时看板/证据/时间轴齐；**历史回放（FR-4 要求）与"两个浏览器一致"在 UI 无对应界面/演示** |
| 5 | 记忆系统（上下文/历史/偏好） | FR-5（`:382-404`）、§12 | 四层记忆、经验库 FTS5、召回注入、晋升技能 | 记忆中心（`06-memory.png`） | FR-5 验收（`:404`） | ⚠️ 经验卡/偏好/工作区记忆齐；**"晋升技能候选"未出现**（§13.3 第 6 条要求） |
| 6 | 异常处理 + 自循环完成 | FR-6（`:406-456`）、§10 | 9 类异常、退避、checkpoint、租约/心跳、turn 预算、三 driver | 运行监控（异常与自愈，`02`）、设置（自动恢复/检查点间隔，`08`） | FR-6 验收（`:456`）、§16.2 | ⚠️ UI 面板齐；**driver 契约不可实现（P1-4）**；turn 预算（10min/20 节点）在设置页无对应项 |
| 7 | 质量门控 + 打分 + 低分返工 | FR-7（`:458-490`）、§11 | 五信号加权、85/70、硬门、回环 3 轮、证据链 | 质量门控（`07-quality.png`）、工作台评分卡 | FR-7 验收（`:490`） | ⚠️ UI 完整（雷达/分布/五信号/回环/人工门/审核记录）；**权重与门控规则与 PRD 冲突（P1-5）**；验收无基线（P1-11） |
| 8 | 借鉴/集成 LoopX | FR-8（`:492-509`）、§3.4、附录 F | 语义对齐、可切换内核、CLI 桥接、失败降级 | 设置-内核选择（`08-settings.png`） | FR-8 验收（`:506-509`） | ⚠️ 设置页有内核选择；**默认值与版本号错（P1-6）**；**checkpoint 协议错（P1-7）**；§16 未覆盖 |

### 5.2 PRD §1.2 六条痛点 × 对应机制 × 验收

| 痛点（`PRD.md:36-43`） | 对应设计 | 验收归属 | 判定 |
|---|---|---|---|
| 1 上下文膨胀/注意力衰退 | Turn Packet（§9.2）、AST 切片（§8.2.3） | 无直接验收条款 | ⚠️ 缺可测项（P2-17） |
| 2 异常即中断 | FR-6 九类异常 + checkpoint + 租约 | FR-6 验收、§16.2 | ✅ |
| 3 质量不可控 | FR-7 五信号 + 硬门 + 证据链 | FR-7 验收 | ⚠️ 无基线（P1-11） |
| 4 经验不沉淀 | FR-5 经验库 + 召回 + 晋升 | FR-5 验收 | ✅ |
| 5 过程黑盒 | FR-4 看板 + 证据 + 时间轴 | FR-4 验收 | ⚠️ 回放缺失（P1-5 表） |
| 6 协作不可编排 | FR-3 DAG + 模板 + 专家 | FR-3 验收 | ✅ |

### 5.3 产品目标 G1–G8（`PRD.md:64-73`）
G1 ⚠️（无 3 步向导 UI）｜G2 ⚠️（画布静态/无拖拽）｜G3 ⚠️（回放/矩阵缺）｜G4 ⚠️（driver 契约缺）｜G5 ⚠️（权重/门控口径冲突）｜G6 ⚠️（"显著下降"不可测）｜G7 ⚠️（checkpoint 协议冲突）｜G8 ✅（插件形态成立）。

---

## 6. UI 截图检查记录

> 截图由 Lead 以完全权限渲染（本子代理沙箱禁止 Chromium 命名管道）；8 屏 + 总览共 **9 张**，均逐张 `read_image` 检查，并对 04/05 做过局部放大与像素抽样。截图 1600×1000（00 为 1600×1060）、无空白、中文无乱码；与 `index.html` 13:15:09 版一致。

| 文件名 | 是否正常 | 问题 |
|---|---|---|
| `00-overview.png` | ✅ 正常 | 8 屏缩略总览，排版整齐；底注"还原提示词 ui-design/PROMPTS.md"现已存在；缩略图 08 偏暗（缩放所致，非缺陷） |
| `01-workbench.png` | ✅ 正常 | 4 KPI + 当前运行 + Agent 实时状态 + 证据流 + 质量快照完整；KPI 口径与 PRD §13.3 的"进行中 Run/节点通过率/平均分/待人工门"不一致（P2）；左下 LoopX v0.9.2（P1-6） |
| `02-monitor.png` | ✅ 正常 | 时间轴/日志/异常自愈/证据链/断点续跑/Agent 矩阵齐全；"并发 4"（P1-5）；日志"9 节点/10 连线"与 05 屏"8 节点/8 连线"冲突（P2-23） |
| `03-agents.png` | ✅ 正常 | 已修为 8 张专家卡（新增 Pinia 迁移专家），筛选 2/4/1/1=8 自洽；Element UI 文案（P2-10）；专家名单与 PRD 附录 B 不一致（P1-5） |
| `04-skills.png` | ✅ 正常（13:15 重渲修复） | 技能表 9 行完整可读、阶段分布/导入/绑定变更齐全；"12 skills"但阶段筛选合计 11（P2-26）；Element UI（P2-10） |
| `05-flow.png` | ✅ 正常（13:15 重渲修复） | 8 节点 8 连线清晰可见（绿实线/琥珀虚线/箭头/标签"通过/≥85/低分回环/≤3 轮"）；属性面板 8 字段完整；CEL/behavior≥80 为 PRD 未定义规则（P1-5/P2-11） |
| `06-memory.png` | ✅ 正常 | 经验卡/偏好/工作区记忆/回灌设置齐全，层级清晰；配色与信息密度良好 |
| `07-quality.png` | ✅ 正常（含口径错误） | 五信号雷达 + 条形 + 分布 + 低分表 + 回环记录 + 审核记录完整；"91.3% 与 71/78"算术不符（P2-9）；权重 25/20/20/15/20 与 PRD 冲突（P1-5）；单信号<60/behavior≥80 为 PRD 未定义规则（P1-5） |
| `08-settings.png` | ✅ 正常（视口截断） | 内核/模型/配额/权重/危险区完整；LoopX v0.9.2 默认 + 自研"无断点"与 PRD 相反（P1-6）；生效配置 JSON 权重冲突；页底"低分文件优先重排/危险区"被截断（P2-22） |

### 6.1 `index.html` 静态检查（已完成，可作为截图的前置证据）
- **8 屏齐全**：`data-page` / `id="page-*"` = workbench、agents、skills、flow、monitor、memory、quality、settings ✅（与 PRD §13.1 一一对应）。
- **完全离线**：无 `<link>`、`<script src>`、`@font-face`、`@import`、`fetch/XHR`；唯一 `http://` 是内联 SVG 的 `xmlns` 命名空间（不发起请求）✅。
- **JS 自洽**：单文件内联脚本约 36 KB，`node --check` 通过；hash 路由 `go()`、`openDrawer/closeDrawer`、命令面板（Ctrl+K）、暂停/继续、重新审查、toast、筛选、`prefers-reduced-motion`、`:focus-visible`、`aria-current/aria-modal` 均在 ✅。
- **DOM 完整性**：id 无重复；68 个 symbol，静态 `<use>` 引用全部命中 ✅。
- **未接真实 API**：无 fetch/EventSource/WebSocket——属"高保真演示稿"定位（PRD §13 称"可交互设计稿"），但**不能作为 SSE/实时链路的可行性证据**；实现阶段需验证 P1-2。
- **动画与截图时序**：`.page.active{animation:pageIn .28s both}`（`index.html:259-260`）要求截屏必须等待动画结束；`screenshot.ps1` 已按 `virtual-time-budget 3500ms` 处理，13:15 重渲全部正常（历史 04 屏骨架态问题已关闭）。

---

## 7. 结论与放行条件

**结论：有条件通过。** 方案与证据基础成立、UI 四件套齐全且质量良好；按以下门槛修订后，本方案具备高置信度可交付性。

### 放行前必须完成（Gate）
1. **冻结 UI 版本并四件套同源**：`index.html`（13:15:09）、9 张截图（13:15–13:16）、`design-spec.md`（13:15:43）、`PROMPTS.md`（13:16:14）需冻结在同一版本；此后任何 UI 改动必须重跑 `screenshot.ps1` 并同步四件套（评审期间 UI 仍在迭代，`00-overview` 13:16:05 晚于截图主体）。
2. **事实修订**：P1-1（热挂载）、P1-2（SSE 鉴权）、P1-3（`/goal gate add`）、P1-7（checkpoint 协议）——四处必须按源码/官方文档改写，不接受"待确认"。
3. **执行契约**：P1-4 必须补一节"Run 驱动契约"：谁创建/持有 driver、Dashboard 点击后的链路、无活跃会话时的 queued 状态与恢复路径，并进 §16.1 验收。
4. **口径统一**：P1-5/P1-6/P1-8（权重、门控、并发、专家/技能、默认内核、LoopX 版本、5 项自建）在 PRD、design-spec、PROMPTS、index.html、截图之间统一；P1-13（三套 tokens）以 index.html + design-spec 为事实源回写 PRD §13.2，并重算 design-spec 的 ink/对比度。
5. **集成方式**：P1-9 重写 design-spec §8 与 PROMPTS §0：Hermes Dashboard 插件 = `manifest.json` + IIFE `dist/index.js`（React 由 `window.__HERMES_PLUGIN_SDK__` 提供）+ `plugin_api.py` router；若坚持独立壳/iframe，则 PRD 必须改交付形态并重估工作量。
6. **验收可测**：P1-11 给出样例项目预期分数基线 + 经验 A/B 口径 + 正确的 SLO 统计方法；否则 FR-7/G6 无法验收。

### 建议在开工前完成（Strongly recommended）
- P1-10（重排 30–45 人日与里程碑）、P1-12（write_approval 叙述）。
- P2-1～P2-27 中的事实精度与文档质量问题（尤其 P2-8 SQL NULL、P2-12 围栏、P2-15 断链、P2-6 Node PATH、P2-19 工具链、P2-16 218 MB 渲染残留、P2-23 跨屏节点数）。

### 通过后的信心判断
- **Hermes 侧**：插件 API、技能、持久化、子代理、hooks、Dashboard 扩展点均有源码级支撑，**"不改核心即可交付"成立**；风险集中在运行时修复（本机 python ACL）与 Dashboard 鉴权细节，均可控。
- **LoopX 侧**：默认自研 + CLI 可选桥接的方向正确，语义对齐可做；但"协议级等价"必须接受 LoopX 没有 checkpoint/list 的事实，不要承诺"两内核完全一致"。
- **产品侧**：8 屏设计稿 + 规范 + 提示词整体质量高于一般交付（信息密度、状态语义、离线自包含、交互真实、A11y 有意识）；主要问题是与 PRD 的口径漂移、tokens 三套并存、集成方式写错——这是文档/收尾问题，不是方案问题。

---

## 8. 附：本次核验方法与局限
- 抽查方式：`read`/`grep` 定向核对源码与官方文档；PowerShell `Get-Content` 对中文文件会因 GBK 解码导致行号漂移，**行号一律以 `read`/`grep`（UTF-8）结果为准**。
- 未能执行：Hermes 实际启动/插件加载/`hermes dashboard`（运行时 python 被 ACL 拒绝，已独立复现 `Access is denied`）；UI 浏览器渲染（沙箱禁止 Chromium 命名管道，截图由 Lead 代渲）。
- 未能独立核实：LoopX 在线 HEAD 与 star 数（本机无法直连 GitHub；以 `research/loopx-analysis.md` 的 GitHub API/raw 原文为 B 级证据）；Hermes v0.22.2 与上游最新版差异（以本机 `install-stamp.json` 的 `d923a5e` 为准）。
- 主要证据文件：`E:\hermes\hermes-agent\hermes_cli\plugins.py`、`plugins_content.py`、`plugins_manifest.py`、`plugins/plugin_storage.py`、`web_server_dashboard.py`、`web_server.py`、`agent/subagent_lifecycle.py`、`agent/error_classifier.py`、`agent/retry_utils.py`、`website/docs/**`、`plugins/kanban/dashboard/plugin_api.py`。

---

# 第二轮增量复审（2026-10-18 13:21–13:25）

> **复审范围**：只复核 Lead 声明的修正项 + 因修正引入的新矛盾 + 截图与 design-spec/PRD 的一致性；不重写首轮报告。
> **版本快照（以 13:25 文件状态为准）**：
> - `docs/PRD.md` 92,599 B / 1,174 行 / 13:17:55；`docs/FEASIBILITY.md` 20,552 B / 246 行 / 13:18:22；`research/hermes-capabilities.md` 52,446 B / 467 行 / 13:18:22。
> - `ui-design/index.html` **293,559 B / 13:22:38**；`design-spec.md` 24,815 B / 346 行 / 13:18:45；`PROMPTS.md` 24,670 B / 336 行 / 13:19:23；`overview.html` 2,925 B / 13:12:46（未重建）；`screenshot.ps1` 13:14:47。
> - `ui-design/screenshots/` 9 张：`00` 13:22:50、`01` 13:20:47、`02` 13:22:47、`03` 13:20:40、`04` 13:20:49、`05` 13:20:48、`06` 13:20:51、`07` 13:21:38、`08` 13:21:40。
> ⚠️ **注意**：`index.html` 13:22:38 晚于多数截图（01/03/04/05/06 为 13:20:4x），UI 仍在迭代；放行前必须冻结版本并重渲一次（见 R7 Gate-1）。

## R1. 复审结论

**可以放行（Conditional Release）**——第一轮 P0/P1 修正**基本到位**，未发现新的阻塞级问题：

- **P0 = 0**（首轮 2 项已关闭：`04-skills.png` 骨架态重渲修复、`design-spec.md`/`PROMPTS.md` 已交付）。
- **P1 = 3**（**均为一句/一段文案级修正**，不涉及方案或实现返工；见 R3）。
- **P2 = 15**（见 R4，均为可并行清理的细节）。
- **另有 1 个放行前操作项**：冻结 UI 版本 + 重渲 9 张截图 + 四件套同源校验（Gate-1）。

一句话理由：核心事实（hot-mount、WebSocket、`/goal gate add`、执行契约、FlowKernel、5 项补足、SQL NULL、工作量、SLO/基线、29 种、32k、api_version）已按源码与首轮意见修正到位；UI 的权重/门控/内核/并发/antdv/91.0%/Top10/8 卡已与 PRD 对齐并通过截图复核；仅剩 3 处文档残留（§14.5 hot-mount 旧句、§3.2 write_approval 旧句、§13.2 栅格旧值）和一次版本冻结。

## R2. Lead 修正项逐条核对

| # | 修正项 | 核对结果 | 证据 |
|---|---|---|---|
| 1 | hot-mount（§3.2/§13.4/§17） | ⚠️ **部分到位**：三处已改，但 §14.5 部署约束仍是旧句 | `PRD.md:114,804,1067` 已正确；**`PRD.md:932` 残留**（见 R3-1）；`FEASIBILITY.md:109,126` 已正确；`hermes-capabilities.md:145` 已正确但 `:451` 残留 |
| 2 | SSE→WebSocket（FR-4/§13.4/§14.5/测试矩阵） | ✅ 到位 | `PRD.md:373-374`（WebSocket + ticket + last_event_seq + 说明为何不用 EventSource）、`:204`、`:805`、`:925`、`:1042`；全文仅 `:374` 以"对比说明"提及 EventSource，不是主张 |
| 3 | `/goal gate add` + 退出码契约（§10.4） | ✅ 到位 | `PRD.md:663`（明确"没有 `--gate` 参数"）、`:668-669`、`:1048`；演练脚本 `:1079-1085` 无旧语法 |
| 4 | 执行契约（REST 不 launch / queued / timeout_seconds） | ✅ 到位 | `PRD.md:664,667-669`（含 `subagent_lifecycle.py:277-280,228` 引用与 `wait(timeout_seconds)` 替代） |
| 5 | FlowKernel 去掉 checkpoint/restore | ✅ 到位 | `PRD.md:502`（协议 5 方法；checkpoint 上移编排层，注明 LoopX 语义） |
| 6 | 5 项补足口径 | ✅ 到位 | `PRD.md:91`；`FEASIBILITY.md:16,171` 一致 |
| 7 | 权重由 UI 对齐 PRD | ✅ 到位 | PRD `:465-469,543` = 20/25/15/25/15；UI `index.html:1965,3174,3321` 与截图 01/07/08、design-spec `:182`、PROMPTS `:40` 全部一致 |
| 8 | 默认内核 UI 改自研 SQLite | ✅ 到位 | UI `index.html:1680,3357-3364`（SQLite Kernel v0.8.4 已连接 / LoopX v2.0.0a1 实验未启用）；PROMPTS `:34`；design-spec `:182`；截图 01–08 左下角均为 SQLITE KERNEL |
| 9 | LoopX pin `>=1.2.4,<1.3` + Node PATH | ✅ 到位（文档） | `PRD.md:505,506`；`FEASIBILITY.md:506`（Hermes node 目录注入 PATH）；UI 版本号仍有小冲突见 R4-4 |
| 10 | SQL claim NULL | ✅ 到位 | `PRD.md:965` `(lease_expires_at IS NULL OR lease_expires_at < :now)` + 说明 |
| 11 | 工作量 30–45 人日 | ✅ 到位 | `PRD.md:980,982`（含拆分口径）；`FEASIBILITY.md:30,221` |
| 12 | SLO/基线可测化 | ✅ 到位 | `PRD.md:1013-1036`（每项 SLO 带统计方法；新增 8 行评分基线 + 允许误差 + 经验 A/B 口径） |
| 13 | `skills.write_approval` 叙述 | ⚠️ **部分到位**：§14.2 已修正，§3.2 仍是旧说法 | `PRD.md:865` 已正确（只门控 `skill_manage`，插件自校验/备份/或走 `dispatch_tool`）；**`PRD.md:110` 残留**（见 R3-2） |
| 14 | 代码围栏/版本号/typo | ✅ 到位 | 全文 24 个 fence（偶数平衡）；版本统一 v2.1（`:5,56,93,130,970,1122`）；"设置在" typo 已消失；§15 标题改"5 个里程碑" |
| 15 | api_version | ✅ 到位 | `PRD.md:1044,1065`；风险表改为"有字段但无强制兼容承诺" |
| 16 | 29 种 FailoverReason | ✅ 到位 | `PRD.md:100,425,1148`；`FEASIBILITY.md:79`；`hermes-capabilities.md:23,305`（均"29 种，覆盖 30+ 语义类别"） |
| 17 | 32,000 字符 | ✅ 到位 | `PRD.md:620`（明确"不是字节，中文按字符计" + 子代理 context 同限） |
| 18 | 8 专家/12 技能 | ⚠️ **部分到位**：数量对齐，名单未完全一致 | PRD `:1101,1105-1114` 8 专家（含**主协调者**）与 12 技能；UI/PROMPTS 8 专家含**记忆归纳**、无主协调者（R4-5） |
| 19 | 附录 E/F | ✅ 已更新 | `PRD.md:1133-1170`（附录 E 证据索引、附录 F LoopX 纠偏均更新；`:1170` 仍保留"五原语非 LoopX 术语"纠偏） |

## R3. 剩余 P1（必须改，均为一句话级修正）

### R3-1　`PRD.md:932`：§14.5 部署约束仍是旧 hot-mount 说法（与 §3.2/§17 矛盾）
- **原文**："`plugin_api.py` 的 `router` 在 **web server 启动时** 挂载…新增/修改后需重启 `hermes dashboard`"。
- **冲突**：同文件 `:114`（hot-mount fallback，新增/新启用插件首次请求现场挂载）、`:1067`（"新增插件可 hot-mount"）；`FEASIBILITY.md:109,126`；源码 `web_server_dashboard.py:899-973`。
- **修法**：改为"新增/新启用插件由首次请求 hot-mount；已挂载路由的 `plugin_api.py` 代码变更需重启；`rescan` 只重扫前端 manifest；未启用/未授权仍 fail-closed（404）"。

### R3-2　`PRD.md:110`：§3.2 关键依据仍称用户技能写入"受 `skills.write_approval` 门控"（与 §14.2 矛盾）
- **原文**：§3.2 第 4 条 "用户自建技能写标准 `~/.hermes/skills/`（受 `skills.write_approval` 门控）"。
- **冲突**：`:865` 已正确说明"只门控 `skill_manage` 工具写入，插件直接 `write_text` 不经过"；`skills.md:668-700`。
- **修法**：把 `:110` 同步为 `:865` 的说法（一行替换）。

### R3-3　`PRD.md:786`：§13.2 栅格仍是旧值（与 design-spec/index.html 矛盾）
- **原文**："左侧导航 **240px**；内容最大宽 **1600px**；卡片圆角 **12px**；间距 4/8/12/16/24/32"。
- **冲突**：design-spec `:45,100,108`（导航 **236px**、内容最大宽 **1680px**、圆角 **3/5/7/9px**、间距 2/4/6/8/9/10/12…）；`index.html:60,257`（`--side-w:236px`、`.view-inner{max-width:1680px}`、`--r-xs..lg:3/5/7/9`）；PRD `:784` 已声明"以设计稿实际实现为准"，`:786` 却未同步。
- **修法**：按 design-spec 改写 `:786`（或删除该行改为引用 design-spec §3.3）。
- **备注**：`PRD.md:784` 的 ink 色值已与 `design-spec.md:62-64`、`index.html:27-31` 对齐（`#A9B5C1/#8B97A4/#5D6976`），首轮 P2-25 已关闭。

## R4. 剩余 P2（15 项，不阻塞放行）

1. **UI 设置页旧文案**：`index.html:3403` "通过阈值 / 低于阈值自动回环" 与新的 70–84 警告通过语义不符（应为"低于 70 自动回环；70–84 警告通过"）。
2. **UI 质量专家提示词残留旧硬门**：`index.html:3824` "硬约束：任一信号 < 60 直接判负" —— PRD 未定义该规则，且 `design-spec.md:124` 明确写"已从设计稿与实现中移除"，二者矛盾；应删除或写回 PRD。
3. **UI 编排节点通过条件残留 `behavior >= 80`**：`index.html:2564` CEL `score >= 85 && behavior >= 80` —— PRD 硬门只有 build 失败/浏览器白屏（`PRD.md:473,700`），design-spec `:124` 称已移除；需统一。
4. **LoopX 版本口径**：UI/PROMPTS 显示 `LoopX v2.0.0a1`（`index.html:3363`；`PROMPTS.md` 相关），而 PRD `:505` pin `>=1.2.4,<1.3`；建议 UI 改为 1.2.4 或标注"2.0.0a1=上游主干实验版，生产 pin 1.2.4"。
5. **专家名单不一致**：PRD 附录 B 8 位含"主协调者（Lead）"（`:1112`）；UI/`PROMPTS.md:17` 8 位含"记忆归纳"、无主协调者。数量对齐但名单不同，需二选一并同步（PRD `:1103` 只宣称数量一致）。
6. **技能计数表述**：`PRD.md:1101` "前序已落地 7 个"但括号内只列 6 个（`vue3-analyze/deps/transform/quality/verify/fix`），第 7 个 `vue3-migrate` 未列；建议补列或改"6 个 + 入口技能"。
7. **"五原语"残留**：`PRD.md:13,102,972` 仍按 LoopX 术语使用，与 `:501,1170` 的纠偏（"五原语不是 LoopX 术语"）不一致；建议改为"借鉴 LoopX 的 turn/quota 语义"或"五原语（我方归纳）"。
8. **行数引用过时**：`FEASIBILITY.md:4` 与 `PRD.md:1157` 仍写 `hermes-capabilities.md（466 行）`，该文件现为 **467 行**；同步即可。
9. **证据文档自相矛盾**：`hermes-capabilities.md:451` 仍写"后端路由需重启 web server 才挂载"，与同文 `:145`（hot-mount）及源码冲突；建议改为与 `:145` 一致的表述。
10. **design-spec §8.4 "SDK 契约（建议）" 与真实 SDK 不符**：虚构 `mount/navigate/api/ws` 方法（`design-spec.md:270-273`）；Hermes 实际暴露 `window.__HERMES_PLUGINS__.register/registerSlot`、`SDK.React`、`SDK.fetchJSON`（`extending-the-dashboard.md:366-417,545,571,893-895`）。建议标注"插件内部封装契约"或改用真实 API 名。
11. **技能阶段筛选计数**：`design-spec.md:154` 与 UI 技能页（截图 04）"全部12 / transform5 / deps3 / quality1 / verify1 / memory1" 合计 11 ≠ 12；补一个阶段或改计数。
12. **评分基线区间歧义**：`PRD.md:1030` "总评分 85–95 ±5" 可读成 80–100，建议改为明确通过窗口（如 "85–95，且不得 <80"）。
13. **overview.html 未随视觉更新**：`overview.html:8-17` 仍用旧 PRD 色 `#0B0F17/#38BDF8/#121826`，与 `index.html`/design-spec 的青绿 `#35CFC1/#07090B` 不一致；建议同步或重生成。
14. **渲染残留**：`ui-design/_src/` 下 30 个渲染临时目录，总计 **218 MB**（浏览器 profile 缓存）；交付/入库前清理并 gitignore。
15. **`08-settings.png` 视口截断**：底部"低分文件优先重排/危险区"被 1000px 视口截断（不影响主体验收，必要时补 full-page）。

## R5. 已关闭 / 新引入项

**已关闭（首轮 → 二轮）**
- `04-skills.png` 骨架态 → 13:20 重渲后 9 行完整可读（截图复核）。
- `05-flow.png` 连线不可辨 → 8 节点 8 连线、箭头/标签清晰（截图复核）。
- `design-spec.md`/`PROMPTS.md` 缺失 → 已交付（24.8 KB / 24.7 KB），内容质量良好。
- SSE→WebSocket、`/goal gate add`、执行契约、FlowKernel、5 项、权重/门控/内核/并发/antdv/91.0%/Top10/8 卡、SQL NULL、30–45 人日、SLO/基线、api_version、29 种、32,000、围栏/版本/typo——全部按首轮意见修正到位（R2）。
- 首轮 P2：`91.3% → 91.0%`、`TreeSelect 68 → 64`（新权重下自洽：`86,0,82,91,81 × 20/25/15/25/15 = 64.4`）、监控日志 `9 节点/10 连线 → 8 节点/8 连线`、ink tokens 三处对齐——均已关闭。

**新引入/需注意（已计入 R3/R4）**
- `index.html` 在截图之后仍被修改（13:22:38 vs 13:20:4x），存在版本漂移（Gate-1）。
- `design-spec.md:124` 声称"任一信号<60/behavior 下限 80 已移除"，但 UI 仍有两处残留（R4-2/R4-3）——说明本轮对齐不彻底。
- UI/PRD 的 LoopX 版本口径、专家名单在修正后出现新的不一致（R4-4/R4-5）。

## R6. 截图复核（第二轮 9 张，逐张 read_image）

| 文件 | 结果 | 关键一致性核对 |
|---|---|---|
| `00-overview.png` | ✅ 正常 | 8 缩略图齐全、排版整齐；底注 design-spec/PROMPTS 均存在 |
| `01-workbench.png` | ✅ 正常 | 91.0% / 均值 88.6 / 64 分回环 / 并发 3/8 / 权重 20/25/15/25/15 / SQLITE KERNEL v0.8.4 全部与 PRD+design-spec 一致 |
| `02-monitor.png` | ✅ 正常 | 8 节点/8 连线（已修）、64 <70、并发 3、SQLite Kernel、WebSocket 语义文案一致 |
| `03-agents.png` | ✅ 正常 | 8 registered · 8 enabled；筛选 2/4/1/1=8；antdv 文案；仅名单口径见 R4-5 |
| `04-skills.png` | ✅ 可读 | 9 行技能全可读、antdv 技能、阶段分布；筛选计数见 R4-11 |
| `05-flow.png` | ✅ 正常 | 8 节点 8 连线、箭头/标签、属性面板阈值 85/回环 3；CEL `behavior>=80` 见 R4-3 |
| `06-memory.png` | ✅ 正常 | 经验卡/偏好/工作区记忆/回灌设置完整；SQLite Kernel |
| `07-quality.png` | ✅ 正常 | 91.0%、回环中 1、未达标 1（RichEditor 67）、TreeSelect 64、OrderDetail 80 警告通过、权重 20/25/15/25/15、门控规则"警告通过 70–84"——全部与 PRD/design-spec 一致 |
| `08-settings.png` | ✅ 正常 | 自研 SQLite 默认 v0.8.4 已连接、LoopX v2.0.0a1 实验未启用、并发 3、权重 20/25/15/25/15、JSON `kernel:sqlite`——与 PRD 一致（LoopX 版本号见 R4-4） |

## R7. 放行条件

**Gate-1（必须，操作项）**：冻结 UI 版本——以最终 `index.html`（当前 13:22:38）为准，重跑 `screenshot.ps1` 重渲全部 9 张，确认 `index.html / screenshots / design-spec.md / PROMPTS.md` 四件套同源；此后 UI 不再改。
**Gate-2（必须，文案级）**：关闭 R3-1（`PRD.md:932`）、R3-2（`PRD.md:110`）、R3-3（`PRD.md:786`）三处 P1。
**Gate-3（建议）**：清理 R4-1～R4-15（可与实现并行；其中 R4-2/R4-3/R4-5/R4-11 属"文档/设计稿一致性"，建议随 Gate-1 一起改，避免再次版本漂移）。

**最终判定：可放行。** P0=0；P1=3（均为一句/一段修正，无方案返工）；P2=15（不阻塞）。相较首轮（P0=2/P1=13/P2=27），修正完成度高，剩余风险集中在"版本冻结 + 三处文档残留"。

## R8. 两轮问题计数对比

| 轮次 | P0 | P1 | P2 |
|---|---|---|---|
| 第一轮（13:00–13:17） | 2 | 13 | 27 |
| 第二轮（13:21–13:25，剩余） | 0 | 3 | 15 |
