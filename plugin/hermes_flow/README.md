# HERMES Flow · Vue2→Vue3 迁移控制面

`hermes_flow` 是 HERMES 的独立插件（`kind: standalone`），把 Vue2 工程迁移到 **Vue3 + Pinia + Vue Router 4 + Vite + ant-design-vue 4** 的过程变成可编排、可观测、可回环、可断点续跑的工程流水线。

- 版本：`0.3.0` · 要求 Hermes `>=0.22` · Python `3.9+`
- 内置资产：**8 个专家**、**12 个技能**、**2 个工作流模板**
- 工具：**34 个 `flow_*` 工具**（专家/技能/工作流/Run/批次/自动 driver/质量/恢复/经验/看板）+ `hermes flow` CLI + `pre_llm_call` 钩子
- 全部内容文件 UTF-8（无 BOM），中文正文

---

## 1. 能力边界

| 能力 | 说明 |
|---|---|
| 专家注册表 | `agents/*.json` 自动加载，支持用户目录覆盖内置；技能 0..N 绑定、模型/工具集/轮次/批次策略可配 |
| 技能库 | 标准 `SKILL.md` 为唯一事实源，按 `phases` / `tags` 筛选，运行时可热替换 |
| 工作流 DAG | 版本化 JSON DSL（`hermes-flow/workflow@1`），节点含 `agent_task` / `batch` / `quality_gate` / `loop` / `human_gate`，环检测 + 拓扑排序强制串行 |
| 批次循环 | 按依赖 wave + 28k 字符预算装箱，默认 **7 文件/批**、并发 1、内层 serial、失败二分拆批（≤2 层）、`staging_apply` 写回 |
| 质量门控 | 五信号加权（AST 20 / 构建 25 / 类型 15 / 浏览器 25 / 行为 15），阈值 85 / 警告 70 / 回环 ≤3 轮 |
| 恢复与记忆 | 异常分类、退避、检查点续跑、SQLite 经验库（召回/沉淀） |
| 可视化 | Dashboard API（`/api/plugins/hermes_flow/...`）+ 静态看板 HTML（`flow_board_render`） |
| 会话命令 | `/flow [status\|agents\|skills\|workflows\|batches\|help]`；Dashboard 侧栏 **Plugins → HERMES FLOW**（`/flow` 页签） |

> 本插件的「主协调者」由 Hermes 编排层承担，不计入 8 张专家卡。

### 1.1 在 Dashboard / 会话中使用

- **侧栏页签**：Dashboard → `Plugins` → **HERMES FLOW**（路径 `/flow`）。
- **会话命令**：在**新开的聊天会话**里输入 `/flow` 或 `/flow status|agents|skills|workflows|batches|help`。
- 若刚安装/更新插件后仍提示 `Unknown command /flow`：关闭旧聊天标签，**新开一个 Chat**（旧 PTY 缓存了旧命令表），或重启 `hermes dashboard`。
- 若 UI 文字发暗/不可见：宿主主题可能把 `--foreground` 解析为透明；插件 CSS 末尾已有字面色兼容覆盖，浏览器强制刷新（Ctrl+F5）即可。

---

## 2. 目录结构

```text
hermes_flow/
├── plugin.yaml                # Hermes 插件清单（工具/钩子声明）
├── __init__.py                # register(ctx)：运行时 + 工具 + CLI + pre_llm_call
├── runtime.py                 # 路径解析、Registry、Run、批次、经验、看板
├── tools.py                   # 34 个 flow_* 工具（JSON Schema + handler）
├── cli.py                     # hermes flow 子命令
├── flow_core/                 # 纯标准库内核（可独立运行/测试）
│   ├── engine/                # DAG、拓扑排序、串行调度器
│   ├── kernel/                # SQLite 持久化内核、状态机、租约
│   ├── batch/                 # 批次规划/队列/存储（FR-10）
│   ├── quality/               # 五信号评分、批级/聚合门
│   ├── recovery/              # 异常分类、退避、检查点、自治循环
│   ├── experience/            # 经验库
│   ├── registry/              # 专家/技能/工作流自动加载
│   ├── adapters/              # LoopX 实验适配层
│   ├── orchestrator.py        # 确定性编排壳
│   └── cli.py                 # python -m flow_core
├── agents/                    # 8 个内置专家 JSON
├── skills/                    # 12 个内置技能（<id>/SKILL.md）
├── workflows/                 # 2 个内置工作流模板 JSON
├── dashboard/
│   └── plugin_api.py          # FastAPI router（Dashboard 后端）
├── tests/                     # 冒烟脚本 + legacy 单测（DAG/调度/质量/恢复…）
├── install.ps1                # Windows 安装脚本
└── install.sh                 # Linux/macOS 安装脚本
```

---

## 3. 安装

### 3.1 Windows（推荐，junction）

```powershell
Set-Location E:\deepSeek\plugin\hermes_flow

# 1) 挂载到 $env:HERMES_HOME\plugins\hermes_flow（默认 E:\hermes）
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

# 2) 启用插件（Hermes 的插件是 opt-in 的）
hermes plugins enable hermes_flow

# 3) 验证
hermes flow status
hermes flow agents
```

脚本行为：

- 校验 `plugin.yaml` / `flow_core` / `tools.py` / `agents` / `skills` / `workflows` 齐全，且 Python 3.9+ 可用；
- 默认创建 **junction**（改源码即时生效）；失败时自动回退为复制；
- **幂等**：已指向同一目录时直接跳过；指向别处时先移动到 `$HERMES_HOME\backups\hermes_flow-<时间戳>` 再重建；
- 打印启用命令、CLI 验证命令与数据目录位置。

常用参数：

```powershell
.\install.ps1 -HermesHome 'D:\hermes'   # 指定 HERMES_HOME
.\install.ps1 -Copy                     # 强制复制（跨卷/权限受限/FAT）
.\install.ps1 -Enable                   # 安装后自动执行 hermes plugins enable
```

### 3.2 Linux / macOS

```bash
cd /path/to/hermes_flow
bash install.sh                    # 默认 $HERMES_HOME 或 ~/.hermes
HERMES_HOME=/opt/hermes bash install.sh
bash install.sh --copy             # 复制模式
bash install.sh --enable           # 安装后自动启用
hermes plugins enable hermes_flow
hermes flow status
```

### 3.3 手动安装 / 开发模式

不跑脚本时，也可手工把插件根链接到 Hermes 插件目录：

```powershell
# Windows（同卷 NTFS）
New-Item -ItemType Junction `
  -Path "$env:HERMES_HOME\plugins\hermes_flow" `
  -Target "E:\deepSeek\plugin\hermes_flow"
```

```bash
# Linux / macOS
ln -s "$(pwd)" "${HERMES_HOME:-$HOME/.hermes}/plugins/hermes_flow"
```

然后执行 `hermes plugins enable hermes_flow`。**Hermes 已运行时需要重启服务或新开会话**，插件才会被重新发现。

> Hermes 通过 `plugins.enabled` 白名单控制插件加载；只在目录里放文件不会自动生效。

---

## 4. 内置专家（8）

数据文件：`agents/<id>.json`，字段为 `id / name / description / role / skills / model / toolsets / max_turns / loop_policy`。
`role` 同时约束职责、输入、输出与禁止事项；`model` 默认 `deepseek-flash`，可在 UI/JSON 中覆盖。

| # | id | 名称 | 绑定技能 | 工具集 | 轮次 | 批次策略 |
|---|---|---|---|---|---|---|
| 1 | `structure-analyst` | 结构分析专家 | `vue3-analyze` | file, terminal | 40 | 关闭 |
| 2 | `dependency-analyst` | 依赖分析专家 | `vue3-deps` | file, terminal | 40 | 关闭 |
| 3 | `code-transformer` | 代码转化专家 | `vue3-transform`、`vuex-to-pinia`、`vue3-router4`、`vue3-antdv` | file, terminal, skills | 60 | **per_batch · 7 文件/批** |
| 4 | `quality-analyst` | 质量分析专家 | `vue3-quality` | file, terminal | 40 | 关闭 |
| 5 | `browser-verifier` | 浏览器验证专家 | `vue3-verify` | browser, terminal, file | 50 | 关闭 |
| 6 | `fix-specialist` | 修复专家 | `vue3-fix` | file, terminal, browser | 50 | 关闭 |
| 7 | `memory-distiller` | 记忆归纳专家 | `experience-distill` | skills, file | 30 | 关闭 |
| 8 | `pinia-migrator` | Pinia 迁移专家 | `vuex-to-pinia` | file, terminal, skills | 60 | 关闭 |

`code-transformer` 的 `loop_policy` 默认值：

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

用户专家写入 `$HERMES_HOME/plugin-data/hermes_flow/agents/*.json`，同名 `id` 覆盖内置；内置专家只能停用、不能删除。

---

## 5. 内置技能（12）

数据文件：`skills/<id>/SKILL.md`。frontmatter 可被 Hermes 技能加载器解析；正文固定 `Procedure` / `Pitfalls` / `Verification` 三段，内容为可执行步骤而非空模板。

| # | id | 名称 | 阶段 | 一句话 |
|---|---|---|---|---|
| 1 | `vue3-analyze` | Vue3 结构分析 | analyze | 文件清单、技术栈、遗留 API、风险与批次建议 |
| 2 | `vue3-deps` | Vue3 依赖分析 | deps | 依赖图、拓扑序、循环分组、版本矩阵 |
| 3 | `vue3-transform` | Vue3 语法升级 | transform | Options→Composition、filters/mixins/this.$xxx |
| 4 | `vue3-quality` | 质量门控评分 | quality | 五信号加权、阈值判定、可定位缺陷 |
| 5 | `vue3-verify` | 浏览器自动化验证 | verify | 路由渲染/交互/控制台/网络证据 |
| 6 | `vue3-fix` | 迁移缺陷修复 | fix | 证据驱动的最小修复与升级策略 |
| 7 | `vuex-to-pinia` | Vuex 到 Pinia 迁移 | transform | store 拆分、调用点、持久化、devtools |
| 8 | `vue3-router4` | Vue Router 3 到 4 迁移 | transform | createRouter、通配符、守卫返回值 |
| 9 | `vue3-antdv` | Ant Design Vue 1.x 到 4.x 映射 | transform | 组件/属性/插槽/图标 + ztree→a-tree |
| 10 | `vue3-vite` | Webpack 到 Vite 配置迁移 | transform | 入口、别名、代理、env、构建 |
| 11 | `vue3-less` | Less 变量与主题迁移 | transform | 变量注入、`:deep()`、antdv 4 主题 |
| 12 | `experience-distill` | 迁移经验归纳 | fix | 经验卡 schema、去重合并、写入经验库 |

> 技能 id 在 frontmatter 的 `id` 字段中显式声明，保证 `agents/*.json` 的 `skills` 引用与目录名一致。

---

## 6. 工作流模板（2）

### 6.1 六阶段主流程 `workflows/vue3-migrate-6phase.json`

```text
结构分析 analyze
   └─> 依赖分析 deps
         └─> 代码转化 transform（batch：7 文件/批 · 28k 预算 · staging_apply）
               └─> 质量门控 quality（五信号 · 85/70 · 回环≤3）
                     ├─(pass)──> 浏览器验证 verify
                     └─(rework)─> 修复回环 fix（≤3 轮，耗尽转人工门）
                                   └──────────┬──────────┘
                                              v
                                        人工验收 review
```

- DSL：`schema: "hermes-flow/workflow@1"`，节点 `depends_on` 与顶层 `edges` 二选一；本模板用 `edges`（`source` / `target`），与 `flow_core.engine.dag.Workflow.from_dict` + `topological_sort` 完全兼容。
- `batch` 节点唯一 schema：`source / order / size / adaptive / context_budget_chars / inner_loop / concurrency / max_split_depth / split_on_failure / quality_gate_per_batch / write_mode`，`files: []` 表示运行时由 Run 传入文件清单。
- 质量门：`signals [ast, build, types, browser, behavior]`、`weights [20,25,15,25,15]`、`pass 85`、`warn 70`、`max_rework 3`。
- `fix` 节点为 `loop` 类型，声明 `when / exit / max_rounds / back_to / on_exhausted`，由运行时条件求值驱动，图中不产生回边以保持 DAG 无环。
- 人工门 `review` 的 `options: [approve, reject, pause]`，超时 24h。

### 6.2 单文件试点 `workflows/single-file-demo.json`

只走「单文件转化 → 质量评分 → 浏览器验证 → 人工确认」，批大小 1、不拆分、回环上限 1。首次接入或换项目时，先用它验证工具链、技能注入、门控与 Dashboard 上报是否正常，再放量到全量批次。

---

## 7. 工具清单（34 个，`toolset=hermes_flow`）

### 专家（5）
`flow_agent_create` · `flow_agent_list` · `flow_agent_get` · `flow_agent_update` · `flow_agent_delete`

### 技能（2）
`flow_skill_create` · `flow_skill_list`

### 工作流（4）
`flow_workflow_create` · `flow_workflow_list` · `flow_workflow_get` · `flow_workflow_validate`

### Run（5）
`flow_run_start` · `flow_run_status` · `flow_run_pause` · `flow_run_resume` · `flow_run_cancel`

### 批次 / 循环（10）
`flow_batch_plan` · `flow_batch_next` · **`flow_batch_auto`** · `flow_batch_status` · `flow_batch_items` · `flow_batch_ingest` · `flow_batch_complete` · `flow_batch_fail` · `flow_batch_split` · `flow_batch_repair`

> `flow_batch_auto` 是自动 driver：认领批次 → 通过 `ctx.subagent_lifecycle` 启动子代理 → 等待/校验 → ingest/apply → 质量门 → 下一批；带单例锁、429 requeue、截断拆批、格式纠正重派、超时取消。**默认开启工作区边界审计**；`concurrency=2|3` 可同 wave 并行（每批独立 worktree，apply/audit 按 seq 串行）。必须在 Hermes agent turn 内调用。

### 质量门控（4）
`flow_gate_score` · `flow_gate_aggregate` · **`flow_quality_collect`** · **`flow_quality_gate`**

> `flow_quality_collect` 执行真实 `npm run build` / `vite build` / typecheck，并用系统 Chrome + CDP 零依赖探针逐路由验证渲染/console/page/network 并截图，返回退出码、耗时、日志尾部、路由结果与 `gate` 字段；`flow_quality_gate` 把真实 build + 批次分数 + 覆盖率 + 浏览器结果合成聚合门。

### 恢复 / 记忆 / 看板（4）
`flow_recovery_classify` · `flow_experience_add` · `flow_experience_search` · `flow_board_render`

所有工具返回 JSON（`{ok, data}` 或 `{ok:false, error, code}`），错误码统一 `FLOW_*`；写操作要求显式 ID/版本，幂等由批次文件级 `(group_id, file_path)` 唯一约束保证。

### 7.1 自动批次 driver 示例（真实子代理）

```text
flow_run_start(workflow_id="vue3-migrate-6phase", project_root="E:\\proj",
               files=[{"path":"src/A.vue","size":129}, ...])
flow_batch_plan(run_id=<run>, node_id="transform")
flow_batch_auto(group_id=<group>, max_batches=3, max_seconds=180, apply=true)
```

`flow_batch_auto` 每次最多推进 `max_batches` 批 / `max_seconds` 秒，返回 `{ok, done, batches_done, batches_total, events[]}`。调用方（agent/cron）可循环调用直到 `done=true`；同一 group 同时只允许一个 driver（文件锁）。

本机实测（2 文件）：子代理 `sa-0-1b999880` 用时 36.9s，完成 2/2 文件、score 97.6、`done=true`，工作区文件由 Options API 改为 `<script setup>`。

此外 `pre_llm_call` 钩子会把活跃 Run 的批次进度与本轮相关经验（按 user_message 召回，≤3 条）压缩到 ≤9,000 字符注入当前 user turn；每次 driver 结束会把失败/限流/截断/越界/修复自动沉淀为经验卡，并写 `memory_distilled` 事件。钩子异常静默，不影响主流程。

---

## 8. CLI（`hermes flow`）

| 命令 | 说明 |
|---|---|
| `hermes flow status` | 打印运行时状态、数据目录、注册数量与最近 Run（JSON） |
| `hermes flow agents` | 列出专家（含内置/用户、技能、loop_policy） |
| `hermes flow skills` | 列出技能（id、名称、阶段、tags、路径） |
| `hermes flow workflows` | 列出工作流模板（不展开 definition） |
| `hermes flow demo --files 287 --batch-size 7` | 确定性六阶段演示：合成 287 文件，跑批、拆批、门控与聚合（无 LLM） |
| `hermes flow plan-batch <files.json> --batch-size 7` | 从文件清单 `[{path,size,deps,risk}]` 生成批次计划 |
| `hermes flow run <workflow_id> --files 20 --project-root <path> --out result.json` | 用 mock runner 跑指定工作流，验证 DAG 与批次编排 |
| `hermes flow verify <project_root> [--timeout 300] [--browser]` | 真实质量采集：build / typecheck / Chrome CDP 路由验证，输出 JSON |
| `hermes flow board --out board.html` | 渲染静态迁移看板 HTML |

内核独立 CLI（不依赖 Hermes）：

```bash
python -m flow_core workflow-demo
python -m flow_core workflow-run --file workflows/vue3-migrate-6phase.json
python -m flow_core --backend sqlite goal-create --title "demo"
```

---

## 9. Dashboard API

后端 router：`dashboard/plugin_api.py`，挂载前缀 `/api/plugins/hermes_flow`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/status` | 运行时概览 |
| GET | `/diagnostics` | 数据目录、插件根、注册错误、Run 数 |
| GET/POST | `/agents` | 专家列表 / 创建专家 |
| GET/DELETE | `/agents/{agent_id}` | 详情 / 删除（内置不可删） |
| GET/POST | `/skills` | 技能列表 / 新建技能（写标准 SKILL.md） |
| GET | `/skills/{id}` | 技能详情 + SKILL.md 正文 |
| GET/POST | `/workflows` | 工作流列表 / 保存与校验 |
| GET | `/workflows/{id}` | 工作流完整 definition（DAG） |
| GET/POST | `/runs` | Run 列表 / 启动 Run |
| GET | `/runs/{run_id}` | Run 详情（含 workflow、批次状态、事件流） |
| GET | `/runs/{run_id}/events?after=<seq>` | 增量事件（断线重放） |
| POST | `/runs/{run_id}/gate` | 人工门批准/驳回 |
| POST | `/runs/{run_id}/nodes/{node_id}/rerun` | 节点级重跑失败批次 |
| GET | `/agent-status` | 专家运行态（活跃 Run/批次） |
| GET/POST | `/memory/experiences` | 经验搜索 / 新增经验 |
| GET | `/quality` | 质量证据列表 |
| POST | `/quality/collect` | 真实 build/typecheck/browser 采集（默认异步 job；`background=false` 同步） |
| GET | `/quality/jobs` | 异步质量任务列表 |
| GET | `/quality/jobs/{id}` | 异步质量任务状态/结果 |
| GET | `/audit` | 越界违规证据 |
| GET | `/drivers` | driver 锁/活跃状态 |
| GET | `/settings` | 数据目录、计数、阈值、driver 限制 |
| POST | `/runs/{run_id}/pause` `/resume` `/cancel` | Run 控制 |
| POST | `/batches/claim` | 认领下一批（返回 Batch Packet） |
| GET | `/groups/{group_id}` | 批次组状态 |
| GET | `/batches/{batch_id}/items` | 批内文件状态 |
| POST | `/batches/{batch_id}/ingest` `/complete` `/fail` `/split` `/repair` | 结果回灌 / 完成 / 失败 / 拆分 / 修复批 |

> Dashboard v2 前端源码在 `dashboard/src/index.js` + `dashboard/src/extra.css`，用 esbuild 构建到 `dashboard/dist/`；旧版 3 Tab bundle 备份为 `dist/index.v1.js` / `style.v1.css`。7 Tab：专家 / 技能 / 工作流 / 运行批次 / 质量 / 记忆 / 设置。

---

## 10. 数据目录

默认 `$HERMES_HOME/plugin-data/hermes_flow/`（插件通过 `plugin_data_dir("hermes_flow")` 解析；独立运行时回退到 `$HERMES_HOME/plugin-data/hermes_flow`）：

```text
plugin-data/hermes_flow/
├── agents/            # 用户专家（按 id 覆盖内置）
├── skills/<id>/       # 用户技能 SKILL.md（同名覆盖内置）
├── workflows/         # 用户工作流模板
├── runs/<run_id>.json # Run 快照（状态、节点、批次组）
├── state.db           # SQLite 内核（Goal/Todo/租约/检查点）
├── batches.db         # 批次组 / 批次 / batch_items（文件级幂等）
├── experience.db      # 经验库
├── staging/<group>/<batch>/  # 子代理 staging 写回区
└── backups/           # staging_apply 前的文件备份
```

升级插件不会清空该目录；`hermes plugins remove` 也只删插件树，数据目录需手动清理。

---

## 11. 测试与自检

在插件根目录执行（使用 Hermes 自带的 Python 或系统 Python 3.9+）：

```powershell
# 1) 核心冒烟：Registry、批次规划、门控、ingest/apply
python tests/smoke_core.py

# 2) 插件注册冒烟：fake ctx 下工具/钩子/CLI 全部注册
python tests/smoke_plugin.py

# 3) Lead 集成冒烟：Run → 批次计划 → ingest/apply → split/repair → orchestrator
#    注意：脚本会在 E:\deepSeek\plugin\.tmp 下建临时目录，若不存在请先创建
New-Item -ItemType Directory -Force E:\deepSeek\plugin\.tmp | Out-Null
python tests/lead_smoke.py

# 4) legacy 单元测试（DAG/调度/质量/恢复/经验/适配器）
python -m unittest discover -s tests/legacy -p "test_*.py" -v

# 5) 自动 driver 单测（成功/截断/格式纠正/429/超时/单例锁）
python -m unittest tests.test_driver -v
python -m unittest tests.test_runtime_driver -v

# 6) 质量采集 + 浏览器探针单测
python -m unittest tests.test_collectors -v
python -m unittest tests.test_browser -v

# 7) 事件流 / 人工门 / 节点重跑 / 记忆闭环 / 压测 / 并行
python -m unittest tests.test_events_gate -v
python -m unittest tests.test_memory_loop -v
python -m unittest tests.test_stress -v
python -m unittest tests.test_parallel -v

# 8) 真实进程 kill/restart 演练（会起子进程；约 10s）
python tests/kill_restart_drill.py

# 9) LoopX 后端 / DAG 编辑 / 异步质量
python -m unittest tests.test_loopx_backend -v
python -m unittest tests.test_dag_edit -v
python -m unittest tests.test_quality_jobs -v
```

内容文件自检（JSON）：

```powershell
python -c "import glob,json; [json.load(open(p, encoding='utf-8')) for p in glob.glob('agents/*.json') + glob.glob('workflows/*.json')]; print('JSON OK')"
```

或直接调用内核校验工作流：

```python
import json
from flow_core.engine.dag import Workflow, topological_sort
for p in ("workflows/vue3-migrate-6phase.json", "workflows/single-file-demo.json"):
    wf = Workflow.from_dict(json.load(open(p, encoding="utf-8")))
    print(p, topological_sort(wf))
```

---

## 12. 已知限制

1. **自动 driver 需要活跃 Hermes turn**：`flow_batch_auto` 依赖 `ctx.subagent_lifecycle`，只能在 agent turn 内工作；`hermes flow run/demo` 仍是确定性 mock runner。子代理的文件/终端工具需要本机有可用 bash（Windows 推荐 Git for Windows；找不到时设置 `HERMES_GIT_BASH_PATH=E:\Git\bin\bash.exe`）。
2. **条件与人工门待接入审批流**：工作流 DSL 已声明 `condition` / `human_gate`，当前执行器按拓扑序推进；条件求值、人工审批持久化与 Dashboard 动作属于后续里程碑。
3. **Dashboard 前端产物**：已含预构建 `dist/index.js` / `style.css` / `manifest.json`，`/flow` 页签可渲染；Dashboard 的自动 driver 按钮尚未接入（当前仅展示状态，driver 从会话/工具调用）。
4. **批次写回**：默认 `staging_apply`（先写 staging，校验后备份并原子应用）；越界写审计依赖批内文件集合与工作区快照，在非 git 工作区需要额外 hash 快照。
5. **经验召回为词面/规则相似度**，不是向量检索；相似度阈值默认 0.82。
6. **LoopX 内核为实验适配层**，默认使用自研 SQLite 内核。
7. **junction 限制**：Windows junction 要求源/目标位于同一 NTFS 卷；跨卷或权限不足时脚本自动尝试 `mklink /J`，再失败则回退复制（也可 `-Copy` 显式指定）。Git Bash / MSYS 下 `ln -s` 可能退化为复制，脚本会检测并提示；复制模式下源改动不会自动同步，需重新执行安装。
8. **测试脚本路径**：`tests/lead_smoke.py` 等沿用开发机绝对路径（`E:\deepSeek\plugin\.tmp`），迁移到其他机器需改临时目录。
9. **Python 依赖**：内核仅用标准库；技能 frontmatter 在 Hermes 内优先用 PyYAML，独立测试自动降级为逐行解析；Dashboard 依赖宿主自带的 FastAPI/Pydantic。

---

## 13. 卸载

```powershell
hermes plugins disable hermes_flow

# junction 模式：只删链接，不删源目录（rmdir 不会跟随 reparse point）
cmd /c rmdir "$env:HERMES_HOME\plugins\hermes_flow"

# 复制模式：直接删除安装目录
Remove-Item -Recurse -Force "$env:HERMES_HOME\plugins\hermes_flow"
```

```bash
hermes plugins disable hermes_flow
rm "$HERMES_HOME/plugins/hermes_flow"          # 符号链接
# 复制模式用：rm -rf "$HERMES_HOME/plugins/hermes_flow"
```

如不再需要数据：先备份，再删除 `$HERMES_HOME/plugin-data/hermes_flow/`。

---

## 14. 编码与贡献约定

- 所有文本文件 **UTF-8 无 BOM**；中文内容不转义（JSON 用 `ensure_ascii=false`）。
- 专家 JSON 字段顺序固定：`id, name, description, role, skills, model, toolsets, max_turns, loop_policy`；`role` ≥20 字且写清职责/输入/输出/禁止事项。
- 技能目录名 = frontmatter `id`；`description` ≤120 字；正文必须包含 `Procedure` / `Pitfalls` / `Verification`。
- 工作流保持无环；节点必须含 `id / name / phase`，边统一用 `source / target`，`batch` 节点必须带完整 `batch` 配置块。
- 修改 `flow_core/**`、`tools.py`、`__init__.py`、`dashboard/**` 前请先跑第 11 节全部冒烟。

---

## 15. CI / 打包 / 版本

```powershell
# 本地 CI（compile + Dashboard 静态冒烟 + 84 单测 + 123 legacy + smoke）
powershell -ExecutionPolicy Bypass -File scripts\ci_local.ps1

# 发布包（输出 dist/hermes_flow-<version>.zip + .sha256）
python scripts\package.py

# Dashboard 静态冒烟（manifest/entry/css/版本一致性）
python scripts\dashboard_smoke.py
```

- 版本：**0.3.0**（`plugin.yaml` / `dashboard/manifest.json` / runtime status 同步）。
- GitHub Actions：仓库根 `.github/workflows/hermes-flow-ci.yml`，Linux 3.11/3.12 + Windows。
- 测试临时目录通过 `FLOW_TEST_TMP` 覆盖；未设置时用系统 temp，便于 CI。
- 质量自动挂载：`flow_batch_auto(..., quality=true, browser=true)` 在批次全部完成后跑 build/typecheck/browser + 聚合门，非 pass 则 Run `gated`。

---

## 16. LoopX / DAG / 异步质量

```powershell
# 查看/切换状态内核
hermes flow doctor
hermes flow --backend loopx doctor
hermes flow backend --set loopx
hermes flow backend --set sqlite
```

- `backend=loopx` 使用 JSONL `LoopXKernel`（`.loopx/domain-state/`），不依赖 `loopx` wheel；真实 CLI 通过 `LoopXBridge` 可选桥接。
- 未知 backend 自动降级 sqlite，并返回 `backend_error`。
- Dashboard 工作流页支持节点拖拽布局、添加/删除节点，位置保存在 `node.meta.x/y`；边仍用 JSON 编辑。
- 质量采集默认异步：`POST /quality/collect` 返回 `job_id`，`GET /quality/jobs/{id}` 轮询；`background=false` 保持同步。

