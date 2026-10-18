# HERMES Flow · Vue2→Vue3 迁移控制面（可行性 + PRD + UI 设计稿）

> 本目录是一份**完整的需求研究与设计方案交付**：可行性结论、PRD、UI 高保真设计稿、LoopX 调研、Hermes 能力证据、独立 QA 报告。
> 目标宿主：**Hermes Agent v0.22.2**（`E:\hermes`）　|　落地场景：大型 Vue2 项目 → Vue3 + Pinia + Vue Router 4 + Vite
> GitHub：https://github.com/cz341003/hermes-flow　|　最新 Release：v0.3.0

---

## 1. 先看结论（30 秒版）

**需求可实现，高置信度；不需要修改 Hermes 核心代码。**

- 交付形态：标准 Hermes 用户插件 `hermes_flow`（`plugin.yaml` + `register(ctx)` + Dashboard tab + CLI）。
- 9 项需求全部有实现路径；其中 **6 项能力需插件补足**：专家注册表、DAG 工作流引擎、批次调度、质量评分卡、结构化经验库、控制面 UI。
- Hermes 原生已具备：技能体系、子代理生命周期、持久化（SQLite/JSON）、异常分类与退避、checkpoint/回滚、会话恢复、浏览器验证、cron、Dashboard UI 插件框架、结构化 LLM 调用。
- 本机唯一阻塞：Hermes bundled Python（`tools\python-3.14.7...`）当前被 ACL 拒绝 → 先跑 `setup-hermes.ps1 -RuntimeOnly` 修复；日志证明插件系统此前正常（52/56 加载成功）。
- 工作量：可演示 MVP 15–18 人日；可上线硬化版 35–50 人日（含批次循环）。
- LoopX：真实存在（6,355★ / Apache-2.0 / CLI+JSON 契约 / 硬需 Node ≥22.22.3），**建议语义借鉴 + 可选 CLI 桥接**，不做唯一内核；前序方案中 `.loopx/domain-state/` 与 `dsh plugin add ...` 两处说法已被纠正（见 PRD 附录 F）。

## 2. 交付物导航

| 交付物 | 路径 | 说明 |
|---|---|---|
| **可行性分析** | [`docs/FEASIBILITY.md`](docs/FEASIBILITY.md) | 需求 2 的正式回答：9 项需求 × Hermes 现状 × 实现路径 × 风险 |
| **PRD（主文档）** | [`docs/PRD.md`](docs/PRD.md) | v2.2：功能需求 FR-1..FR-10、架构、数据模型、调度/异常/质量/记忆、批量循环、UI 设计、实现方式、里程碑、验收 |
| **UI 可交互设计稿** | [`ui-design/index.html`](ui-design/index.html) | 单文件离线可开，8 屏（hash 路由：`#workbench` `#monitor` `#agents` `#skills` `#flow` `#memory` `#quality` `#settings`） |
| **UI 总览** | [`ui-design/screenshots/00-overview.png`](ui-design/screenshots/00-overview.png) | 8 屏缩略合集 |
| **UI 截图** | [`ui-design/screenshots/`](ui-design/screenshots/) | 1600×1000，9 张（00–08） |
| **设计规范** | [`ui-design/design-spec.md`](ui-design/design-spec.md) | IA、tokens、组件/状态、交互、响应式、可访问性、Dashboard 集成 |
| **还原提示词** | [`ui-design/PROMPTS.md`](ui-design/PROMPTS.md) | 逐屏可复刻提示词 |
| **Hermes 能力证据** | [`research/hermes-capabilities.md`](research/hermes-capabilities.md) | 466 行，全部 `源码:行号`：插件 API/技能/子代理/记忆/恢复/UI 框架/运行时 |
| **LoopX 调研** | [`research/loopx-analysis.md`](research/loopx-analysis.md) | 440 行：仓库事实、状态模型、CLI、集成方案、前序纠偏 |
| **批量循环调研** | [`research/batch-loop-analysis.md`](research/batch-loop-analysis.md) | 批次拆分 + 子代理循环：Hermes 批量通道证据、A–E 方案对比、批规划算法、状态机、B1–B10 验收 |
| **独立 QA 报告** | [`research/qa-review.md`](research/qa-review.md) | 独立评审：事实核验 50 处、需求覆盖矩阵、问题清单与放行条件 |

## 3. 如何查看

```powershell
# 打开 UI 可交互设计稿（离线，无外部依赖）
start E:\deepSeek\ui-design\index.html

# 看总览截图
start E:\deepSeek\ui-design\screenshots\00-overview.png

# 看 PRD / 可行性
notepad E:\deepSeek\docs\PRD.md
notepad E:\deepSeek\docs\FEASIBILITY.md
```

## 4. 需求 → 方案映射（一页）

| # | 需求 | 方案要点 | PRD 章节 |
|---|---|---|---|
| 1 | 自定义 Agent + 技能并自动加载 | Agent/Skill Registry（SQLite），prompt→专家、技能绑定、启动自动加载；技能走标准 `SKILL.md` | FR-1、FR-2、§9 |
| 2 | 展示已加载 Agent/技能 | Hermes Dashboard 插件 tab `/flow`（manifest + IIFE JS + FastAPI router） | FR-2、§13.4、§14.5 |
| 3 | 自定义协作流程 | JSON DSL DAG（agent/batch/quality/human/condition/loop/join/script）+ 调度器 + 模板库 | FR-3、§8 |
| 4 | 可视化流程与 Agent 状态 | 工作台/监控/编排 3 屏 + WebSocket 实时事件 + 证据抽屉 + 历史回放 | FR-4、§13.3 |
| 5 | 记忆系统 | 四层记忆（turn 切片/run 状态/经验库/偏好）+ `pre_llm_call` 召回注入 + FTS5 | FR-5、§12 |
| 6 | 异常处理 + 自循环 | 异常分类/退避/断点续跑/租约心跳/turn 预算；driver=cron、`/goal`、前台会话 | FR-6、§10 |
| 7 | 质量门控 + 低分回环 | 五信号评分（AST20/构建25/类型15/浏览器25/行为15）+ 85/70 门控 + ≤3 轮回环 + 证据链 | FR-7、§11 |
| 8 | 借鉴/集成 LoopX | 五原语语义对齐；默认自研 SQLite；LoopX 仅 CLI 子进程可选后端（失败降级、单写者） | FR-8、§3.4、附录 F |
| 9 | 大批量拆批 + 子代理循环 | 拓扑分层 + 预算装箱 → 批次队列；每批一个子任务，子代理批内循环文件；批间串行/同层可并行；文件级幂等 + 批级拆分/断点 | FR-10、§8.4、§9.4、附录 G |

## 5. 关键设计决策

1. **Hermes 只做运行时，HERMES Flow 做控制面**：不在插件里重写 LLM 循环，只治理状态/调度/门控/记忆。
2. **串行是引擎硬约束**：拓扑排序 + 租约，非 prompt 软约束。
3. **Turn Packet 切片**：每节点只注入当前切片（≤32,000 字符）+ 相关经验，避免长上下文注意力衰退。
4. **质量门控必须可追溯**：每个分数都有证据（命令/退出码/日志/截图/LLM rubric），低分自动回环、超限人工门。
5. **自治有边界**：turn 预算 + 多级上限 + 无进展检测 + 危险动作人工门，避免"自动跑飞"。
6. **UI 不自建壳**：设计稿是独立演示壳，落地为 Dashboard `/flow` tab 内 8 个子页，复用宿主侧栏/顶栏。
7. **复用前序资产**：`vue3migrate-core`（123 单测）已验证的状态内核/引擎/质量/恢复/经验可迁入 `core/`。
8. **批量循环（FR-10）**：批次是治理单元、文件是幂等单元；staging-apply 写入（防越界/防重复）、批级 AST/diff 门 + 聚合级全量门、driver 单例 + 心跳 + 断点对账。

## 6. 已验证 / 未验证

**已验证**
- 前序内核端到端实跑（PM Python 3.14.7）：`done=True`，18 文件平均 100 分，trace 含 429 退避与低分回环重试（仅因沙箱禁止写 `E:\hermes` 的经验库停在最后一步）。
- Hermes 插件 API/技能/子代理/Dashboard 扩展点等 50 处源码抽查通过（QA）；批量通道事实另行抽查 20 处（`delegate_task` 10 并发/24k、lifecycle 8 并发/32k/无 output_schema 等）。
- UI 9 张截图全部真实渲染、可读、信息自洽；批次循环（批次队列/wave/专家循环配置/×43 节点/批量设置）已并入 01/02/03/05/07/08 并复核。

**未验证（环境限制）**
- 本机 `hermes` 全入口当前不可执行（bundled Python ACL 拒绝），因此**插件加载 / Dashboard tab / 端到端迁移未在本机实跑**；修复运行时后按 PRD §16 验收。
- LoopX 真机未安装，桥接层未实测；方案基于官方文档与 CLI 契约。

## 7. 建议的下一步

1. 修复运行时：`E:\hermes\hermes-agent\setup-hermes.ps1 -RuntimeOnly`，按 `hermes doctor` → `plugins list` → `dashboard` 自检。
2. 确认 PRD 的 4 个开放问题（单插件领域包、并发/turn 预算、阈值可配、多项目并行）。
3. 进入 M0：插件骨架 + Dashboard tab + hot-mount 验证。
4. 先做「单文件转化 → 评分 → 回环」最小链路，再扩展到六阶段与批量。

---

## 8. 实现进展（2026-10-18）

**MVP 插件已实现、测试并安装到本机 Hermes。**

- 源码：[plugin/hermes_flow](plugin/hermes_flow)　|　实现报告：[docs/IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md)　|　插件说明：[plugin/README.md](plugin/hermes_flow/README.md)
- 已安装：`E:\hermes\plugins\hermes_flow`（复制模式；`config.yaml` 已启用 `hermes_flow`，备份 `config.yaml.bak-hermes_flow-20261018`）
- 规模：**34 个 `flow_*` 工具**、8 专家、12 技能、2 工作流模板、**Dashboard v2（7 Tab）**、`hermes flow` CLI、`pre_llm_call` hook
- 验证：新单测 **84/84**、前序回归 **123/123**、E2E **20 文件 10 批全部 applied**、工具层 E2E **5/5 批**、287 文件 demo **67/67 批**、`hermes plugins doctor` 通过
- **R1 自动 driver 已完成**：`flow_batch_auto` 通过 `ctx.subagent_lifecycle` 启动真实子代理；2 文件 live E2E：36.9s、2/2 done、score 97.6、`done=true`，工作区改写为 `<script setup>`
- **R2 真实 20 文件迁移已完成**：sample-app → `plugin/r2-work`，**8/8 批、20/20 applied、全部 pass（97.0–97.6）**；19 个文件改写为 Vue3 + Pinia + Router4 + Vite，报告 [docs/R2_REPORT.md](docs/R2_REPORT.md)
- **R3 真实质量门已完成**：flow_quality_collect 抓出缺失 vite.config.js；补后 vite build 通过（3180 modules、8.92s），Chrome CDP 验证 4/4 路由、聚合门 **pass 97.22**；报告 [docs/R3_REPORT.md](docs/R3_REPORT.md)
- **R4 写入边界审计已完成**：基线快照 + 每批 apply 后审计，越界 created/modified/deleted 自动回滚、标记 `FLOW_BATCH_WRITE_SCOPE`、Run 置 gated；报告 [docs/R4_REPORT.md](docs/R4_REPORT.md)
- **R5 Dashboard v2 已完成**：专家/技能/工作流/运行批次/质量/记忆/设置 7 Tab，真实 API；Chrome CDP 7/7 Tab 渲染、console 0 错误；报告 [docs/R5_REPORT.md](docs/R5_REPORT.md)
- **R5b 收尾已完成**：持久化事件流 + cursor 断线重放、人工门批准/驳回、节点级重跑、工作流 JSON 编辑；报告 [docs/R5B_REPORT.md](docs/R5B_REPORT.md)
- **R6 记忆闭环已完成**：`pre_llm_call` 每 turn 自动召回经验并注入；批次失败自动沉淀（write_scope/rate_limit/truncation/rework/failure）；报告 [docs/R6_REPORT.md](docs/R6_REPORT.md)
- **R8 压测已完成（调度上界）**：1000 文件 → 150 批/50 wave；700 文件 → 100 批 + 10 次注入故障，100/100 done、0 failed、110 launch、3.95s；报告 [docs/R8_REPORT.md](docs/R8_REPORT.md)
- **R7 同 wave 并行已完成**：`concurrency=1..3`，每批独立 worktree，apply/audit 按 seq 稳定提交；3 批 0.552s→0.235s、max_active=3；报告 [docs/R7_REPORT.md](docs/R7_REPORT.md)
- **R8b 真实并行/崩溃恢复已完成**：真实 6 文件 3 批并行 79s 全 pass；kill worker 后租约/锁过期，新进程 attempt=2 恢复 2/2 批、8/8 文件；报告 [docs/R8B_REPORT.md](docs/R8B_REPORT.md)
- **R10 工程化已完成**：测试可移植（`FLOW_TEST_TMP`）、GitHub Actions（Linux/Windows）、`ci_local.ps1`、`package.py` 打包 **0.2.0 zip + sha256**、质量自动挂 driver（`quality=true`）；报告 [docs/R10_REPORT.md](docs/R10_REPORT.md)
- **R9 LoopX + 体验项已完成**：`flow --backend loopx` / JSONL LoopXKernel / doctor / 降级；DAG 拖拽编辑；异步质量 job（`/quality/jobs`）；报告 [docs/R9_UX_REPORT.md](docs/R9_UX_REPORT.md)
- **WebUI 自定义入口已补齐**：专家/技能可直接新增，工作流可复制模板后拖拽/表单/JSON 编辑；步骤见 [docs/USAGE_CUSTOMIZE.md](docs/USAGE_CUSTOMIZE.md)
- **工作流编辑体验**：React Flow 完整可视化连线（拖拽/端口连线/MiniMap），保留表单+JSON 编辑；修复模板选中态与「添加节点」；调研见 [docs/WORKFLOW_EDITOR_RESEARCH.md](docs/WORKFLOW_EDITOR_RESEARCH.md)
- 待办：1000 文件真实 LLM 预算验证；发布 v0.3.0（R9/DAG/异步质量超出 v0.2.0 Release）；真实 loopx CLI 联调（可选）；详细清单见 [docs/REMAINING_TASKS.md](docs/REMAINING_TASKS.md)


---

> 说明：本目录所有交付物为设计/方案阶段成果，代码骨架与插件安装属于下一阶段；`plugin/reference_core/` 是从前序工程复制来的**只读验证副本**（用于实跑内核），`plugin/test-output.txt` 为测试原始输出。
