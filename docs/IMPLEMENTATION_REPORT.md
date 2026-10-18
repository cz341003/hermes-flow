# HERMES Flow 实现报告（v0.2.0）

> 目标：把 PRD v2.2 的"长周期多智能体迁移控制面"落成可加载、可测试、可安装的 Hermes 插件。
> 产物：`E:\deepSeek\plugin\hermes_flow`（源码）+ `E:\hermes\plugins\hermes_flow`（已安装）
> 日期：2026-10-18

---

## 1. 交付状态

| 项 | 状态 | 说明 |
|---|---|---|
| Hermes 插件清单 / 注册 | ✅ | `plugin.yaml` + `register(ctx)`；`hermes plugins doctor` 通过，注册 **34 tools / 1 hook** |
| 专家 / 技能 / 工作流注册中心 | ✅ | 8 专家、12 技能、2 工作流模板，启动自动加载；用户目录可覆盖；校验（role/skills/loop_policy/DAG） |
| 工作流 DAG | ✅ | 版本化 JSON DSL；环检测/拓扑排序；`agent_task / batch / quality_gate / human_gate / loop` |
| **批次循环（FR-10）** | ✅ | 拓扑分层 + 预算装箱、批次队列、原子认领/租约抢占、ingest/apply（staging + backup + `applied_hash`）、split/repair、组策略生效、批次 id 跨组唯一 |
| **自动批次 driver** | ✅ | `flow_batch_auto`：claim → `ctx.subagent_lifecycle` launch → wait/校验 → ingest/apply → 质量门 → complete/fail → next；429、截断拆批、非法 JSON 纠正一次、超时取消、文件单例锁 |
| 质量门控 | ✅ | 批级 AST/diff/白名单 + 聚合级全量门；**R3 真实 build/typecheck/Chrome 浏览器采集已实现并通过**（R2 产物聚合门 pass 97.22） |
| 异常/恢复 | ✅ | 异常分类、退避/重试、租约过期重认领、split 上限、repair 上限、断点对账 |
| 经验库 | ✅ | SQLite 经验沉淀/召回；**R6 每 turn 自动召回注入 + 批次失败自动沉淀**（write_scope/rate_limit/truncation/rework/failure） |
| **R6 记忆闭环** | ✅ | `pre_llm_call` 注入相关经验（≤9k）+ 活跃 Run 进度；driver 结束自动沉淀并写 `memory_distilled` 事件；报告 `docs/R6_REPORT.md` |
| **R8 压测** | ✅（调度上界） | 1000 文件 → 150 批/50 wave；700 文件 → 100 批 + 10 次注入故障，100/100 done、0 failed、110 launch、3.95s；报告 `docs/R8_REPORT.md` |
| **R7 同 wave 并行** | ✅ | `concurrency=1..3`；同 wave 多批并发、每批独立 worktree、apply/audit 按 seq 串行；3 批 0.552s→0.235s、max_active=3、stable_order=true；**真实 6 文件 3 批 79s 全 pass**；报告 `docs/R7_REPORT.md` |
| **R8b 真实进程/并行** | ✅ | 真实 6 文件并行 3/3 done、6/6 applied；kill worker 后租约/锁过期，新进程 attempt=2 恢复 2/2 批、8/8 文件；修复线程池 contextvar 丢失 bug；报告 `docs/R8B_REPORT.md` |
| **R10 工程化** | ✅ | 测试可移植（`FLOW_TEST_TMP`）、GitHub Actions（Linux/Windows）、`scripts/ci_local.ps1`、`scripts/package.py` 打包 0.2.0 + sha256、质量自动挂 driver（`quality=true`）；报告 `docs/R10_REPORT.md` |
| **R9 LoopX** | ✅ | `backend=sqlite|loopx`、JSONL `LoopXKernel`、`flow --backend`/`doctor`/`backend --set`、未知后端降级 sqlite；报告 `docs/R9_UX_REPORT.md` |
| **DAG 拖拽编辑** | ✅ | 绝对定位节点 + SVG 连线 + 添加/删除 + meta.x/y 保存；CDP 7→8 节点、拖拽生效、console 0 |
| **异步质量任务** | ✅ | `QualityJobManager` + `/quality/jobs`；实测 job 29.22s、build/browser 4/4 pass；UI 后台轮询 |
| Dashboard | ✅（R5） | **7 Tab v2**：专家/技能/工作流/运行批次/质量/记忆/设置；React SDK 源码 + 19KB IIFE；真实 API；Chrome CDP 7/7 Tab 渲染、0 console error |
| **R5 Dashboard** | ✅（主体） | 专家运行态、技能正文、工作流只读 DAG、Run 节点/批次/文件、质量采集、记忆搜索/新增、设置/driver/audit；报告 `docs/R5_REPORT.md` |
| **R5b Dashboard 收尾** | ✅ | 持久化事件流 + cursor 断线重放、人工门批准/驳回、节点级重跑、工作流 JSON 编辑；报告 `docs/R5B_REPORT.md` |
| CLI | ✅ | `hermes flow status/agents/skills/workflows/demo/plan-batch/run/verify/board` |
| 安装 | ✅ | 已复制安装到 `E:\hermes\plugins\hermes_flow`；`config.yaml` 已启用；`.env` 已加 `HERMES_GIT_BASH_PATH` |
| 真实子代理 E2E | ✅ | 2 文件真实迁移：子代理 36.9s、2/2 done、score 97.6、`done=true`、工作区改写为 `<script setup>` |
| **R2 真实 20 文件迁移** | ✅ | sample-app 20 文件 → **8 批/5 wave，8/8 done、20/20 applied、全部 pass（97.0–97.6）**；19 个文件真实改写（Vue3+Pinia+Router4+Vite）；报告 `docs/R2_REPORT.md` |
| **R3 真实 build** | ✅ | `flow_quality_collect` 抓出 R2 缺失 `vite.config.js`（Vite 未启用 Vue 插件）；补配置后 `vite build` 通过：3180 modules、8.92s、dist 产出；采集器 5/5 单测；报告 `docs/R3_REPORT.md` |
| **R3 浏览器验证** | ✅ | Chrome + 零依赖 CDP 探针，`/`、`/home`、`/users`、`/about` 4/4 路由渲染正常、0 console/page/network 错误、截图留存；`flow_quality_gate` → **pass(97.22)** |
| **R4 写入边界审计** | ✅ | 基线快照 + 每批 apply 后审计；越界 created/modified/deleted 自动回滚、`FLOW_BATCH_WRITE_SCOPE`、Run `gated`；4 个 audit 单测 + driver drift 集成测试；报告 `docs/R4_REPORT.md` |

---

## 2. 代码结构（已实现）

```
E:\deepSeek\plugin\hermes_flow\
├── plugin.yaml                # 34 tools + pre_llm_call
├── __init__.py                # register(ctx)：runtime + tools + CLI + /flow + hook
├── runtime.py                 # Registry/Kernel/BatchQueue/Experience/Run + 自动 driver 适配
├── tools.py                   # 34 个 flow_* 工具
├── cli.py                     # hermes flow 子命令 + 确定性 demo
├── flow_core/
│   ├── kernel/                # 前序 durable state（Goal/Todo/Gate/Evidence/Checkpoint）
│   ├── engine/                # DAG + 串行调度器（123 单测）
│   ├── batch/
│   │   ├── models.py          # FileItem/BatchPolicy/Plan/Record
│   │   ├── planner.py         # 拓扑 wave + 预算装箱
│   │   ├── store.py           # SQLite 批次/条目/回执/租约/requeue/split/repair
│   │   ├── queue.py           # claim/ingest/apply/组策略
│   │   └── driver.py          # 自动 driver：子代理生命周期 + 恢复 + 门控
│   ├── quality/               # 五信号评分 + batch_gate（批级/聚合）
│   ├── recovery/              # 异常分类/退避/checkpoint/自治循环
│   ├── experience/            # 经验库
│   ├── registry/              # 专家/技能/工作流自动加载与校验
│   ├── adapters/              # LoopX 实验适配（未接入插件）
│   └── orchestrator.py        # 确定性工作流编排壳
├── dashboard/
│   ├── manifest.json          # tab /flow + entry/css/api
│   ├── dist/index.js|css      # 预构建 IIFE + 宿主透明色兼容
│   └── plugin_api.py          # FastAPI router
├── agents/ skills/ workflows/ # 8 / 12 / 2 内置内容
├── tests/                     # 59 个新单测 + 123 legacy + e2e/smoke
├── install.ps1 / install.sh
└── README.md
```

---

## 3. 验证结果（本机实测）

| 验证 | 命令 | 结果 |
|---|---|---|
| 插件注册 | `hermes plugins doctor hermes_flow --ci` | ✅ manifest/import/register 通过；34 tools + 1 hook |
| 新单测 | `python -m unittest discover -s tests -q` | ✅ **84/84** |
| 前序回归 | `python -m unittest discover -s tests\legacy -q` | ✅ **123/123** |
| 自动 driver 单测 | `python -m unittest tests.test_driver tests.test_runtime_driver -v` | ✅ 9/9：成功 apply、截断拆批、非法 JSON 纠正、429 requeue、超时、单例锁、runtime 端到端 |
| 端到端（mock） | `python tests/e2e_demo.py` | ✅ sample-app 20 文件 → 10 批/6 wave，10/10 done、20/20 applied、聚合门 97.6，`done=True`；重复 apply 幂等 |
| CLI demo | `hermes flow demo --files 287` | ✅ 287 文件 → 67 批全部 done（mock runner） |
| 工具层 E2E | `python tests/smoke_tools_flow.py` | ✅ 34 工具注册 → Run → batch plan/next/ingest/complete → gate → 经验/看板 |
| Dashboard API | FastAPI TestClient（安装副本） | ✅ `/status` 200：8 专家 / 12 技能 / 2 工作流 |
| Dashboard 页签 | 无头 Chrome 打开 `http://127.0.0.1:9119/flow` | ✅ 侧栏 **Plugins → HERMES FLOW**、8 专家卡、4 KPI、三 Tab 渲染（截图 `docs/assets/dashboard-flow.png`） |
| UI 文字可见性 | CDP 审计三个 Tab 计算样式 | ✅ 修复宿主 `--foreground=transparent` 导致的文字透明；三 Tab `invisible=0` |
| **真实子代理 E2E** | `hermes chat --oneshot` 调 `flow_run_start → flow_batch_plan → flow_batch_auto` | ✅ 2 文件真实迁移：子代理 `sa-0-1b999880`，36.9s，2/2 done、score 97.6、`done=true`；A/B.vue 改为 `<script setup>`；未改批外文件 |
| **R2 20 文件真实迁移** | `r2_setup.py` + `flow_batch_auto`（真实 lifecycle） | ✅ **8/8 批、20/20 applied、全部 pass（97.0–97.6）**；b0004/b0006 各重试 1 次；19 个文件改写；package.json→Vite5/Vue3/Pinia/Router4；7 个 `.vue` 全部 `<script setup>` |

> 真实 E2E 需 Git Bash 可用；本机已把 `HERMES_GIT_BASH_PATH=E:\Git\bin\bash.exe` 写入 `E:\hermes\.env`。

---

## 4. 已实现的 FR-10 / driver 关键语义

- **批次规划**：依赖图拓扑排序 → wave 分层 → 28k 字符预算装箱；默认 7 文件/批；高风险文件单独成批。
- **批次队列**：`claim_next` 原子认领 + CAS；租约过期抢占；组策略从 `batch_groups.policy_json` 生效；429 时 `requeue` 不消耗 attempt。
- **写入治理**：子代理只写 staging；`apply` 备份→临时文件→原子替换→`applied_hash`；`batch_items UNIQUE(group_id,file_path)`。
- **自动 driver**：`BatchAutoDriver` 封装 launch/wait/result/cancel；结果 JSON 校验（容忍围栏/前后说明）；非法 JSON 一次纠正重派（B13）；文件锁保证单 driver（B14）；截断 split；低分 repair；超时 cancel。
- **质量门**：批级 AST/diff/白名单硬门；聚合门 build/browser/coverage + 加权 ≥85。
- **断点续跑**：批次/文件状态持久化；`applied_hash` 幂等。

---

## 5. 安装与启用

### 5.1 已完成的安装

```powershell
powershell -ExecutionPolicy Bypass -File E:\deepSeek\plugin\hermes_flow\install.ps1 `
  -HermesHome E:\hermes -Copy
```

- `E:\hermes\plugins\hermes_flow`（复制模式）
- `E:\hermes\config.yaml` 的 `plugins.enabled` 已加入 `hermes_flow`（备份 `config.yaml.bak-hermes_flow-20261018`）
- `E:\hermes\.env` 已加入 `HERMES_GIT_BASH_PATH=E:\Git\bin\bash.exe`（备份 `.env.bak-hermes_flow-20261018`）
- 运行时已修复，Dashboard 运行在 `http://127.0.0.1:9119`，`/flow` 页签可用

### 5.2 自检

```powershell
hermes plugins list --plain --no-bundled
hermes plugins doctor hermes_flow --ci        # 期望 34 tools / 1 hook
hermes flow status
hermes flow demo --files 287
```

---

## 6. 已知限制 / 后续工作

| 限制 | 影响 | 后续 |
|---|---|---|
| driver 只做同步单 group | **R7 已支持同 wave 并行（≤3）**；跨 wave 仍串行 | 可扩展更多并发/跨 wave |
| 1000 文件真实 LLM 迁移 | 调度层已证明，真实 token/时延成本未跑 | 按真实 6 文件 79s 粗估 1000 文件约 3.5–4h wall；预算项 |
| kill/restart 100 批演练 | 已完成 8 文件真实进程 kill/restart（attempt=2 恢复） | 100 批杀进程演练可扩展 |
| 记忆不自动召回注入 | 经验库需显式调用 | **R6 已完成**：每 turn 召回注入 + 批次自动沉淀 |
| Dashboard 可视化编辑 | 已支持 JSON 编辑 + 只读 DAG；拖拽式 DAG 编辑未做 | 后续体验优化 |
| 质量采集为显式调用 | 尚未在 driver 聚合时点自动执行 | 工程化接入 |
| LoopX 未接 | **R9 已接 JSONL LoopXKernel + CLI/doctor/降级** | 真实 loopx CLI wheel 未安装；桥接保留 |
| 条件 / 人工门 | DSL 已声明，执行器未求值 | 后续里程碑 |
| 质量任务同步 | **已改异步 job + UI 轮询** | job 为内存态，重启丢失（证据文件保留） |
| DAG 编辑 | **已支持拖拽布局/增删节点/meta 保存**；边仍用 JSON 编辑 | 后续端口连线 |
| Windows shell | 子代理需 Git Bash | 已写 `HERMES_GIT_BASH_PATH`；换机需配置 |
| 测试无 CI | **R10 已加 GitHub Actions + 本地 ci_local.ps1** | 已解决 |
| 打包/版本 | **0.2.0 zip + sha256** | 发布需 Git tag/Release |

---

## 7. 下一步建议

1. 1000 文件真实 LLM 迁移（预算项）。
2. 发布新版本（R9/DAG/异步质量已超出 v0.2.0 Release 内容）。
3. 真实 `loopx` CLI 安装联调（可选）。
4. 端口级 DAG 连线、WebSocket 推送（体验）。

---

## 附：关键命令

```powershell
$py = "E:\hermes\installs\9249f73cb9b5d199\pm-runtime\generations\08c2ecb7c45c4c4e96e026b29d30c0bb\Scripts\python.exe"
cd E:\deepSeek\plugin\hermes_flow
& $py -m unittest discover -s tests -q
& $py -m unittest discover -s tests\legacy -q
& $py tests/e2e_demo.py
```
