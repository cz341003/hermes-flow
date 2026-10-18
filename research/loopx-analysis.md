# LoopX 调研与 Hermes Agent 集成方案

> 调研对象：GitHub `loopx-project/loopx`
> 基线 commit：`105c4bc15091afac832495167cb98a1389951a04`（2026-10-17T20:05:56Z，main 分支）
> 调研时间：2026-10-18（Asia/Hong_Kong）
> 产出范围：本文件 + `E:\deepSeek\research\loopx\`（clone 失败，见 §附录 B）
> 证据分级：✅ = 源码/API/文档原文核验；⚠️ = 仅官方文档自称或二手搜索结果；❌ = 网传/前序产物自称，未获真实验证

---

## 0. 一页结论

**LoopX 是什么**：一个真实存在、活跃度极高（6.3k star / 604 fork / 156 open issues，2026-05-31 建仓，2026-10-18 仍在推送）的「长周期 Agent 控制面」。它**不是** Agent 框架、不是 runtime，而是给已有 harness（Codex App/CLI、Claude Code、DeepSeek Harness、KunlunCode、OpenCode、Pi、ZCode、Kiro、Cursor…）外挂的一层**持久状态内核**：Goal / Todo / Gate / Evidence / Quota / Turn Receipt 的记账与准入。Apache-2.0（v0.4.8 起，此前 MIT），形态是「**Python 命令行壳 + TypeScript 控制面**」：pip 包 `dependencies = []`，但硬性要求系统 Node ≥ 22.22.3（pip 装不了 Node）；主干 `pyproject.toml` 已是 `2.0.0a1`，发布线仍是 1.x。

**值不值得集成**：值得"借鉴 + 可选桥接"，**不值得“直接内嵌为唯一内核”**。原因：
1. 它的**稳定契约是 CLI + JSON 输出**（官方明说「The state and CLI contracts are the stable center」），Python 模块不是公共 API——架构测试 `test_control_plane_has_no_unreviewed_outward_dependencies` 反而**禁止** control-plane 被外部层导入（`docs/architecture.md`「Current Dependency Budget」）。所以 `import loopx.*` 属于踩红线用法。
2. 它**已经有一个官方 DSH 插件**（`packages/dsh-loopx-plugin`，含 GoalBar Web 路由、Driver、shadow observer）。但这个插件绑定的是 **DSH 的 Loader/Web/GoalBar 体系**，**Hermes 无法复用**——它既不是 Hermes 插件，也不能通过 `dsh plugin add github:loopx-project/loopx` 安装（官方 README 明确说这条 URL 会选到 monorepo 根、报 `index file missing: index.js`）。
3. 真正可复用的是它的**协议**：`host-integration-surface-v0`（thin hook / lifecycle reads / controlled writes / CLI fallback / compact projection）。这套协议与 Hermes 的 `PluginContext`（register_tool / register_hook / register_cli_command / state / current_cron_execution / subagent_lifecycle）几乎一一对位。

**推荐方案：C（混合）** —— 保留 Hermes 自研内核为默认后端（零依赖、可离线），**按 LoopX 语义重写五原语的字段与状态机**，同时把现状那段"风格模拟"的 `LoopXBridge` 升级为**真正可用的 CLI 子进程后端**（固定 argv、`--format json`、失败降级）。不 import LoopX，不依赖 dsh 插件，不做双写。
工作量：首版 5~7 人日，硬化 2 周；风险集中在 LoopX 版本漂移（需 pin 版本 + 契约测试）与「双内核单一写者」纪律。

**最需要纠正的前序认知**（见 §6.1）：PRD §12 与 README §8 中「`.loopx/domain-state/<goal>/*.jsonl` 是 LoopX 账本」**是我方自创的布局，LoopX 里没有这个目录**；「`dsh plugin add github:loopx-project/loopx` 可作内核」**对 Hermes 无效且 URL 用法错误**；「五原语」是 Hermes 的抽象命名，**不是 LoopX 的术语**（LoopX 用六层存储 + 四种运行时职责 + Turn 契约）。

---

## 1. 仓库事实（可核验）

| 项 | 值 | 证据 |
|---|---|---|
| URL | https://github.com/loopx-project/loopx | ✅ GitHub API |
| 默认分支 / HEAD | `main` / `105c4bc15091afac832495167cb98a1389951a04`（2026-10-17T20:05:56Z，author huangruiteng，PR #6767） | ✅ `/commits?per_page=1` |
| License | **Apache-2.0**（SPDX `Apache-2.0`）；README 注明 **v0.4.8 起改为 Apache-2.0**，v0.4.7 及更早为 **MIT**（保留 `LICENSE-MIT`） | ✅ API `license` 字段 + README「License」节 + 根目录 `LICENSE` / `LICENSE-MIT` / `NOTICE` |
| 主语言 | Python（API `language: Python`）；control-plane 有 TS 迁移中（`tsconfig.control-plane.json`、`loopx/control_plane/turn_driver/settlement.ts`） | ✅ API + `docs/architecture.md`「Turn Decision Vocabulary」表 |
| 规模/活跃度 | stars 6355，forks 604，watchers 6355，open issues 156，repo size ≈177 MB；创建 2026-05-31，最近 push 2026-10-18T04:43:26Z | ✅ API `/repos` |
| 活跃度旁证 | PR/Issue 编号已到 #6767（HEAD commit 引用），`docs/` 下有 RFC/协议/benchmark 数百篇；Discord、Lark/WeChat 渠道 | ✅ commit message + 根目录结构 |
| Topics | `agent-control-plane`, `agent-harness`, `dsh-plugin`, `local-first`, `long-horizon-agents`, `multi-agent`, `codex`, `claude-code` … | ✅ API `topics` |
| 运行时前置 | `requires-python = ">=3.11"`（无上限）；**Node.js ≥ 22.22.3 是硬要求**（控制面是 TypeScript，pip 装不了 Node） | ✅ `pyproject.toml` 原文 + README「Requires Python 3.11+ and Node.js 22.22.3+」 |
| Python 依赖 | **`dependencies = []`（零运行时依赖）**；可选 extras：`deepseek-harness`（`deepseek-harness-sdk==0.1.5rc1`）、`test`、`public-source-reader` 等 | ✅ `pyproject.toml` 原文 |
| 打包形态 | 控制面以 **TypeScript 源码随 Python 包分发**（`[tool.setuptools.package-data]` 含 `loopx.control_plane.*/*.ts`、`*.json`）；SKILL 装到 `share/loopx/skills/*` | ✅ `pyproject.toml` 原文 |
| 版本线 | 发布线为 **1.x**（README「LoopX 1.0 is a usable local control plane」；dsh 插件要求 ≥1.2.4；搜索结果提及 `v1.4.2`⚠️）；但 **main 分支 `pyproject.toml` 已是 `version = "2.0.0a1"`** —— 主干处于 2.0 pre-alpha | ✅ `pyproject.toml`（2.0.0a1）+ README/插件 README（1.x 线）；v1.4.2 仅搜索旁证 |

**关键目录（根，✅ API `contents/`）**

```
apps/            presentation（dashboard/desktop）
benchmark/       LHTB / SWE-Marathon 等基准与数据
demo/workspace/  可复现 Workspace 场景
docs/            architecture.md、state-interaction-model.md、reference/protocols/*.md、rfcs/
loopx/           Python 内核：control_plane/、hosts/、capabilities/、goal_mode_*.py、operator_gate.py、paths.py …
packages/        dsh-loopx-plugin（独立版本化的 DSH 插件包）
man/             命令手册
skills/          workflow skills（$loopx / /loopx 入口）
tests/           含 tests/architecture/test_control_plane_import_boundaries.py
pyproject.toml / setup.py / mkdocs.yaml / package.json / tsconfig.control-plane.json
```

`loopx/` 下已核验存在（✅ 目录 listing）：`control_plane/`、`hosts/`、`capabilities/`、`canary/`、`presentation/`、`goal_mode_mcp.py`、`operator_gate.py`、`authority.py`、`history.py`、`paths.py`、`global_todos.py`、`heartbeat_prompt.py`、`long_task_cadence.py`、`chat_*.py`、`*_goal_mode/`（agy / kiro_cli / kunluncode / opencode / opencode2 / pi …）等。

---

## 2. 架构与状态模型

### 2.1 六个持久层（`docs/architecture.md`「Architecture」节，✅ 文档原文）

1. **Registry**：已知 goal 列表 + repo / adapter / authority / status / guards；
2. **Goal state**：单个 goal 的 active state 文件；
3. **Run log**：每 goal 的 JSON + Markdown 报告；
4. **Run history**：agent / heartbeat / UI 消费的紧凑索引；
5. **Status / attention queue**：首屏"谁该动"；
6. **Compute quota**：本地策略，限自动 agent 的算力消耗。
> 另有可选 **probe surface**（`--next-probe`），明确声明"`next_probe` 不校验只读性，执行策略另行要求只读"，**不是第七层**。

### 2.2 四种运行时职责（同上「Runtime Responsibility Model」，✅）

| 职责 | 拥有 | 不得拥有 |
|---|---|---|
| Agent | 规划、分析、工具调用、一次有界执行 | 持久 goal 生命周期、无界写入授权 |
| Provider | 外部调用、有界观测、effect 结果、readback | 领域转移策略、todo 状态 |
| Capability | 面向调用方的结果契约、领域策略、观测归一化、校验、类型化转移提案 | 调度、claim、gate、直接写生命周期 |
| **LoopX Kernel** | goal / todo / claim / gate / monitor / quota / 已接受 writeback / 恢复 / 调度 | 领域推理、provider 实现细节 |

执行路径 `Agent → Capability → Provider`，控制路径 `Provider readback → Capability transition → Kernel`。

### 2.3 状态存储的真实布局（✅ `loopx/paths.py` 常量与函数）

```python
DEFAULT_RUNTIME_ROOT    = Path.home() / ".loopx"
LEGACY_RUNTIME_ROOT     = Path.home() / ".codex" / "loopx"
DEFAULT_PROJECT_REGISTRY= Path(".loopx") / "registry.json"
DEFAULT_PROJECT_GOALS   = Path(".loopx") / "goals"
LEGACY_PROJECT_GOALS    = Path(".codex") / "goals"
GLOBAL_REGISTRY_FILENAME= "registry.global.json"
def default_goal_state_file(project, goal_id):   # → <project>/.loopx/goals/<goal_id>/ACTIVE_GOAL_STATE.md
```

即：**项目内 `.loopx/registry.json` + 每 goal 一份 Markdown `ACTIVE_GOAL_STATE.md`**；机器级 `~/.loopx/registry.global.json` 与 `~/.loopx/runtime/goals/<goal>/…`（含 rollout 事件日志，见 `paths.py` 中 `DEFAULT_ROLLOUT_EVENT_LOG_NAME` 的识别逻辑）。存在 legacy `.codex/goals` 迁移路由与 `requires_single_goal_state_route()` 的**双路冲突拒绝**逻辑（✅ 函数体）。

**重要纠偏**：LoopX 曾有一版「Todo 事件溯源 JSONL（`events.jsonl`）」，已被 PR #5054 **明确退休**：`docs/reference/protocols/event-sourced-state-contract-v0.md` 原文「This experimental protocol is retired by PR #5054. There is no current `loopx.event_sourced_state` API, Todo event replay, Markdown backfill or event completion route.」现役 Todo 存储是「legacy Markdown **或** 选定的 File/SQLite authority」。→ **前序产物里"对齐 LoopX 的 `.loopx/domain-state/` JSONL 账本"是虚构布局**（见 §6.1）。

### 2.4 四个产品 actor（`docs/state-interaction-model.md`「Actors」，✅）

- **Goal**：持久工作对象，拥有 objective / 当前状态 / authority sources / guards / run history / next handoff；「goal 不是 chat thread」。
- **Executor（原文写 Codex App executor）**：临时执行者，只做有界转移，不持有真相。
- **User**：边界、奖励（`human_reward` overlay）、私有材料、生产/破坏性动作的唯一授权源。
- **Dashboard**：只读为主的投影，「不是真相来源」；写操作必须 opt-in + preview + loopback。

文档中的硬不变量（✅ 原文「Invariants」）摘：
- active goal state 是持久上下文，chat 只是执行上下文；
- 每个有意义的 state-only 更新都需要一次 `refresh-state` run，dashboard 才看得见；
- `human_reward` 不等于写授权；
- UI filter / 选中行是浏览器状态，不是 goal 状态；
- 未知 status 字段是 additive（向前兼容），改已有字段语义必须升契约。

### 2.5 生命周期状态机（`state-interaction-model.md` mermaid，✅）

```
Registered → Ready → QuotaCheck
QuotaCheck → UserGate | AwaitEvidence | Running | QuietNoop | Repair
Running → Writeback | Repair
Writeback → Ready（refresh-state + spend）| Done（objective terminal）
```

---

## 3. 「五原语」与 turn 语义（精确定义）

### 3.1 术语澄清（必须先说清）

- **LoopX 自己没有「五原语」这个词**。「五原语」出自 Hermes PRD §12（`E:\DHLocal\HERMES\docs\PRD.md:425`，`should-run/claim/update/refresh-state/spend-slot`）——它是**对 LoopX 五个 CLI 生命周期动作的归纳**，恰好真实存在，但不能当 LoopX 的官方模型。
- LoopX 自己的切分是：**六个持久层**（§2.1）+ **四种职责**（§2.2）+ **Turn 契约词汇**（§3.2）+ **五个产品承诺问题**（README「Core Control-Plane Promises」：objective / next / human judgment / evidence / continuation）。
- README 列出的 shipped primitives 原话是：lifetime goals、concrete user gates、audited safe fallbacks、peer todo ownership、quota and steering、compact run history、evidence-backed handoff（✅ 原文）。**checkpoint / receipt 不是并列"原语"，而是 Turn 结算与恢复的机制名**。

### 3.2 Turn 语义（✅ `docs/reference/protocols/turn-controller-contract-v0.md`）

- 词汇表**由数据文件拥有**：`loopx/control_plane/turn_loop_controller_contract_v0.json`，生成 Python/TS 绑定（`scripts/generate_turn_contract.py`，`--check` 确定性校验，禁止手改）。
- 三套词表分开、保持既有拼法：**TurnResultKind（执行后结果）**、**LoopXTurnRoute（执行前路由）**、**loop disposition（循环处置）**。
- 公开投影示例（原文代码）：
  ```python
  from loopx.control_plane.turn_driver import LoopXTurnRoute, project_turn_route
  assert project_turn_route(LoopXTurnRoute.BLOCKED).value == "wait"
  ```
  `wait` 与 `blocked` 都投影为 `wait`；`contract_error` 抛 `ValueError`，不是 disposition。
- 决策**不是** result-kind → route 的字符串映射：`decide_loop_disposition(receipt, quota_decision, predecessor_turn_key, budget)`；同一个 `validated_progress` 可能立即继续、耗尽后重规划、让位给用户 gate、或需要 capability adapter。
- 生成契约含 **29 条有序规则：10 条 admission + 19 条 return**，首个命中生效；Python controller 是唯一求值者，TS 只导出数据/类型与投影。
- `docs/architecture.md` 补充：`terminal_closeout_failed` = 已持久 writeback + 已 spend 后终态收口失败，恢复必须**重试同一 Turn 的 closeout**，不得重复已提交 effect。

### 3.3 五个生命周期动作的真实语义与必需参数（✅ `host-integration-surface-v0.md`「CLI Fallback」原文命令）

| Hermes 叫法 | 真实 CLI | 语义 | 关键约束 |
|---|---|---|---|
| `should_run` | `loopx --format json --registry "$HOME/.loopx/registry.global.json" quota should-run --goal-id <G> --agent-id <A>` | 本 turn 能否花钱/交付；返回 `interaction_contract`、`goal_boundary`、`next_cli_actions` | **是唯一交付闸门**；必须带 goal+agent；advisory 字段不得当授权 |
| `claim` | `loopx todo claim --goal-id <G> --todo-id <T> --claimed-by <A>`（硬租约再加 `--agent-id --claim-operation-id --task-lease-idempotency-key --task-lease-expected-version`） | 认领切片，写 `claimed_by`（软）/ `task_lease_v0`（硬，opt-in） | 竞争单元是 `(goal_id, todo_id)`；stale lease/重复 claim 必须 fail closed |
| `update` | `loopx todo complete … --evidence "<public-safe evidence>"` / `todo update` / `todo supersede` | 回写结果与证据 | 手上有 lease 时必须带 key+version，否则拒绝 |
| `refresh_state` | `loopx refresh-state --goal-id <G> --agent-id <A>` | 让 dashboard/status 追上状态 | 有 vision checkpoint 语义：`ok=true` ≠ checkpoint satisfied |
| `spend_slot` | `loopx quota spend-slot --goal-id <G> --todo-id <selected> --slots 1 --source heartbeat --execute --agent-id <A>` | 记账一次**已验证**的自动 turn | 先验证证据再花；每 turn 最多一次；指定 todo 绑定；`receipt` 是幂等键 |

**Rule 0（原文「Acceptance Checks」第 1 条）**：`quota should-run` 永远是第一道交付闸门。
**静默跳过**（`monitor_quiet_skip`）不花配额，但要提交 receipt + no-spend stall 观测。

### 3.4 Gate / Evidence / Receipt / Checkpoint 的真实位置

| 概念 | 真实载体 | 证据 |
|---|---|---|
| Gate | 用户 todo（`--task-class user_gate|user_action`）+ `loopx operator-gate --decision approve|reject|defer`；`blocks_agent` / `global_gate` 决定是否停整条 lane | ✅ host-integration「Controlled Writes」+ state model「Actors」 |
| Evidence | `todo complete --evidence` 的 public-safe 文本 + run index 紧凑行 + `human_reward` overlay；**原始日志/trace 必须留在宿主侧** | ✅ 同上 + 「Public/Private Boundary」 |
| Receipt | Turn 结算凭据：绑定 turn id、写回、spend 一次、可重放；重复 retry 用同一 `--turn-instance-id` | ✅ dsh 插件 README「Driver retry boundary」 |
| Checkpoint | 不是独立存储：是「checkpointed boundary authority」+ vision checkpoint（决定是否需要 rebase 旧决策） | ✅ state model「Agentic RL Boundary Model」 |

---

## 4. CLI / API / Dashboard

### 4.1 CLI（以 README + 协议文档原文为准，✅）

```bash
# 安装与技能
python3 -m pip install --upgrade loopx && loopx workflow-skills --install

# 日常只读
loopx status                 loopx diagnose / doctor [--deep]
loopx history --goal-id G    loopx review-packet --goal-id G [--format json]
loopx quota should-run --goal-id G --agent-id A
loopx capability list --format json
loopx configure-goal --goal-id G         # 只读能力目录，--execute 才写
loopx preset list / show daily-triage    # 只读
loopx serve-status                       # 本地状态服务
loopx dashboard / loopx dash             # 浏览器/PWA 与 session dash

# 启动与接入
loopx start-goal --guided --project . --goal-text "..."
loopx agent-onboard --agent-type codex-app-ssh --project .
loopx heartbeat-prompt [--thin] --goal-id G --agent-id A
loopx worker-bridge                      # 通用 worker 桥
loopx --registry .loopx/registry.json resolve-agent-thread \
      --host-surface deepseek-harness-native --thread-id <SESSION_ID>

# 写
loopx todo add / claim / update / complete / supersede
loopx operator-gate --decision approve|reject|defer
loopx refresh-state --goal-id G --agent-id A
loopx quota spend-slot --goal-id G --todo-id T --slots 1 --source heartbeat --execute
loopx task-lease acquire|renew|transfer|release|inspect
loopx reward ... --dry-run              # 再显式写
```
（以上命令名均在 README 或 `host-integration-surface-v0.md` 原文出现；`--help` 未逐条核验。）

**CLI 入口（✅ `pyproject.toml` `[project.scripts]` 原文）**：

```toml
loopx                            = "loopx.entrypoint:main"
loopx-kunluncode                 = "loopx.kunluncode_goal_mode.cli:main"
loopx-lark-provider              = "loopx.extensions.lark.provider:main"
loopx-openviking-history-export  = "loopx.extensions.openviking_semantic_preference.history_export:main"
loopx-openviking-semantic-preference = "loopx.extensions.openviking_semantic_preference.provider:main"
```

→ 集成 Hermes 时只应依赖第一个（`loopx`），其余是 provider 扩展入口，与 Hermes 无关。

### 4.2 Python / TS API（⚠️ 有，但**不是**对外稳定契约）

- `pyproject.toml` 层面：**没有**任何 Python 公共 API 承诺（`dependencies = []`，无 `[project.entry-points]` 之外的导出面；控制面是随包分发的 TS）。这进一步支持"CLI 是 ABI"的判断。
- Python 侧真实存在的入口（原文出现过）：`from loopx.cli import build_parser`、`from loopx.cli_commands.support_control_chat import chat_server_options`、`from loopx.chat_server import serve_chat`（✅ 出自 host-integration 文档「Native Chat startup from a trusted launcher」）。
- 内核模块：`loopx/control_plane/turn_driver/{driver.py,transaction.py,settlement.ts,loop_controller.py}`、`loopx/control_plane/turn_loop_controller_contract_v0.json`（✅ 文档引用 + 目录 listing）。
- MCP：存在 `loopx/goal_mode_mcp.py`（✅ 目录 listing）；协议文档只把 MCP 定义为「薄 facade，不得绕过 CLI 语义」（✅ host-integration「Roles」）。
- **结论**：对外集成应以 CLI + JSON 为 ABI。`docs/architecture.md`「Current Dependency Budget」明确用架构测试**拒绝** control-plane 被 present/CLI/capability 层以外导入——反向说明外部项目 import 内核属于不受支持路径。

### 4.3 Dashboard（✅）

- `loopx dashboard` 是受支持的浏览器/PWA 启动路径；桌面 App 复用同一 loopback 服务与 Goal state（README）。
- `loopx dash` 是「session dash」实时单页面板（sessions / goals / 进度 / 统计，自动刷新）。
- 代码位置 `apps/presentation/dashboard/`（根目录 listing）+ 设计文档 `docs/product/surfaces/session-dash-panel-design.md`。
- 安全边界：默认 loopback、非真相源、写需显式 capability + preview + 同操作 CLI fallback（host-integration「Roles」/「Controlled Writes」）。

---

## 5. 与 Hermes Agent 的集成点

### 5.1 Hermes 插件能力面（✅ 源码核验，`E:\hermes\hermes-agent\hermes_cli\plugins.py`）

| Hermes 能力 | 位置 | 对应 LoopX 契约 |
|---|---|---|
| `register(ctx)` + `plugin.yaml`（`provides_tools` / `provides_hooks` / `requires_env` / `requires_auth` / `config_schema` / `python_dependencies`） | `plugins.py:230` `PluginContext`；`hermes_cli/plugins_manifest.py` | 宿主接入面 |
| `ctx.register_tool(name, toolset, schema, handler, check_fn, requires_env, is_async, description, emoji, override)` | `plugins.py:456` | Lifecycle reads / Controlled writes 暴露为模型工具 |
| `ctx.register_hook(name, cb)`，`VALID_HOOKS` 见 `plugins.py:109-204`：`pre_tool_call`、`post_tool_call`、`transform_tool_result`、`pre_verify`、`on_session_start/end/finalize`、`subagent_start/stop`、`pre_command`、`pre_llm_call`、`transform_llm_output` … | `plugins.py:933` | thin hook activation（只做路由，不嵌调度） |
| `ctx.register_cli_command(name, help, setup_fn, handler_fn, description)` | `plugins.py:633` | CLI fallback（`hermes loopx …`） |
| `ctx.state`（profile 级持久 JSON）、`get_config/set_config` | `plugins.py:282,266,278` | 绑定关系（goal_id, agent_id, session→thread） |
| `ctx.current_cron_execution()` | `plugins.py:404` | 定时/心跳 turn 的 `turn_instance_id` 与幂等 spend |
| `ctx.subagent_lifecycle` | `plugins.py:386` | 多 agent（peer）协作与子代理归属 |
| `ctx.spawn_task` / `ctx.on_unload` | `plugins.py:418,409` | 心跳轮询、子进程清理 |
| `ctx.register_system_prompt_section` / `register_middleware` / `register_auxiliary_task` | `plugins.py:957,937,853` | 注入 `interaction_contract.primary_action`（薄注入，≤ 固定字符预算） |

### 5.2 映射建议（Hermes 插件 ↔ LoopX 宿主契约）

| Hermes 侧 | 做法 | 依据 |
|---|---|---|
| 工具 | 6 个只读/受控写工具：`loopx_status`、`loopx_should_run`、`loopx_todo_claim`、`loopx_todo_update`、`loopx_refresh_state`、`loopx_spend_slot`；全部 `subprocess` 固定 argv、`--format json`、带 timeout、禁 shell、解析失败 fail closed | host-integration 的 Lifecycle Reads / Controlled Writes / CLI Fallback |
| Hook | `pre_tool_call`：若目标是受保护写（发布/生产/git push）则要求本次 turn 的 `quota should-run` 已放行 + 存在 `todo_id`；`pre_verify`：交付前校验 evidence 是否已写入；`on_session_end`：补一次 `refresh-state`（摘要级）；`subagent_start/stop`：绑定 peer 身份 | thin hook activation 六步 + 「Acceptance Checks」 |
| Cron | 用 `current_cron_execution()` 生成稳定 `--turn-instance-id`；只消费 `scheduler_hint` 做节奏，不自己决定优先级 | README「Scheduler cadence follows quota should-run.scheduler_hint」 |
| 子代理 | 每个子代理分配 `agent_id`（注册到 `coordination.registered_agents`），claim 同一 `(goal_id, todo_id)` 竞争单元 | state model「Peer Task Coordination」+ architecture「Peer Task Coordination」 |
| 状态目录 | LoopX 侧：`<project>/.loopx/registry.json`、`<project>/.loopx/goals/<goal>/ACTIVE_GOAL_STATE.md`、`~/.loopx/registry.global.json`；Hermes 侧：`ctx.state` 只存**绑定表**（session↔thread↔goal↔agent），不复制 Goal/Todo 真相 | `loopx/paths.py` + 「单一写者」 |
| 降级 | `loopx doctor` 失败 → 工具返回 `unavailable` 并让上层用自研内核；绝不假装成功 | host-integration「CLI Fallback」+ `models` 工具 `check_fn` |

### 5.3 明确不可复用的部分

- **`packages/dsh-loopx-plugin` 不能装进 Hermes**：它是 DSH 的 package（`cordis.patch.yml` / Loader rows / `/api/loopx.goalbar` Connection 路由 / DSH Session 事件），依赖 DSH 的 Web 服务器与客户端槽位（✅ plugin README 原文）。
- **`dsh plugin add github:loopx-project/loopx` 是错的**：官方 README 明确「this plugin package ... `git+https://github.com/loopx-project/loopx.git` cannot select the nested, built plugin」，并在 marketplace 场景报 `entry file missing: index.js`（✅ 原文）。正确安装是 release tarball 或 `dsh plugin --profile web add dsh-loopx-plugin` —— **且只对 DSH 有意义**。

---

## 6. 集成方案对比与推荐

### 6.1 先评估现状：前序产物 vs 真实 LoopX（差距核验）

前序产物：`E:\DHLocal\HERMES\vue3migrate-core\vue3migrate_core\adapters\loopx_adapter.py`（530 行）、`docs\PRD.md:423-427`（§12）、`README.md:291-306`（§8）；已随插件 vendored 到 `E:\hermes\plugins\vue3_migration\vue3migrate_core\`（51 个文件）。

| 前序声明 | 真实情况 | 判定 |
|---|---|---|
| `loopx_adapter.py:6-8`「文件布局与稳定键 upsert 语义对齐 LoopX 的 `.loopx/domain-state/` 设计」；`README.md:297,304` 同 | LoopX 无 `.loopx/domain-state/`；真实为 `.loopx/registry.json` + `.loopx/goals/<goal>/ACTIVE_GOAL_STATE.md`（`loopx/paths.py`）；JSONL 事件溯源已被 PR #5054 退休 | ❌ **风格模拟**，不是对齐 |
| `loopx_adapter.py:76,115`「对齐 `upsert_domain_state_jsonl` 语义」 | 未在 LoopX 找到该函数/契约（文档与 listing 均无）；当前存储是 Markdown / File / SQLite authority | ❌ 未证实 |
| 「五原语 `should_run/claim/update/refresh_state/spend_slot`」（`loopx_adapter.py:235,253,283,326,352`） | 五个动作真实存在，但 CLI 是 `quota should-run` / `todo claim` / `todo {update,complete}` / `refresh-state` / `quota spend-slot`，且 **must-run 参数更多**（`--goal-id`、`--agent-id`、`--todo-id`、`--slots`、`--source`、`--execute`、`--claimed-by`） | ⚠️ 语义方向对，参数/字段未对齐 |
| `LoopXBridge`（`loopx_adapter.py:470-504`）实现 `resolve-agent-thread` 与 `quota should-run --turn-instance-id` | `resolve-agent-thread` 真实（dsh 插件 README 原文）；但 `quota should-run` **缺 `--goal-id`/`--agent-id`**，也没有 `--format json` 之外的稳定输出约定；**没有** `spend-slot` 桥接、没有 receipt/幂等、没有 doctor 探测 | ⚠️ 半成品，不可直接切真实后端 |
| 状态机 `GoalStatus.PLANNING/RUNNING/WAITING_GATE/PAUSED/DONE`、todo `READY/CLAIMED/DONE/BLOCKED/FAILED`（`loopx_adapter.py:171-200,227-233`） | LoopX 侧真实状态机是 `Registered→Ready→QuotaCheck→{UserGate,AwaitEvidence,Running,QuietNoop,Repair}→Writeback`（`state-interaction-model.md`）+ `interaction_contract.mode` 十余种模式 | ⚠️ 自洽但**不同构**；切换会丢语义（尤其 QuietNoop/Repair/scope mismatch） |
| `LoopXKernel` 用文件锁 + 原子替换写 JSONL（`loopx_adapter.py:49-128`） | 工程质量尚可（Windows/POSIX 锁、tmp+replace），但 LoopX 侧写入是「active-state file lock + 乐观 revision + lease epoch」（architecture「Local Server / Daemon Roadmap」第 1-2 步） | ✅ 可用但≠等价（无 revision/lease 语义） |
| PRD「默认用自研轻量版（TypeScript）」（`PRD.md:148,384`） | 实际落地是 **Python**（adapter + `vue3migrate_core`），PRD 与实现不一致 | ⚠️ 文档漂移，需修正 |
| PRD「`dsh plugin add github:loopx-project/loopx`」（`PRD.md:149,426`） | 对 Hermes 完全无效（那是 DSH 插件）；且该 URL 安装方式本身被官方否掉 | ❌ 需删除 |

**一句话结论**：前序 adapter 是**有工程价值的"语义仿真层"**（能跑、可切、零依赖），但它模拟的是**想象中的 LoopX**；作为自研内核的"schema 预演"可以保留，作为「真实 LoopX 后端」则必须重写桥接层。

### 6.2 三方案对比

| 维度 | **A 自研内核（语义对齐，零依赖）** | **B 直接嵌入/桥接 LoopX** | **C 混合（自研默认 + LoopX 可选，CLI 桥）** |
|---|---|---|---|
| 具体做法 | 保留 `vue3migrate_core`，按 LoopX 语义重写 Goal/Todo/Gate/Quota/Receipt 字段与状态机；`backend` 工厂不变 | 所有状态交给 LoopX CLI；Hermes 只做领域包 + 质量门控 + 技能；或 `import loopx.*` | 默认 A；`--backend loopx` 时全部读写走 CLI 子进程；绑定表存 `ctx.state`；`doctor` 失败自动降级 |
| 工作量 | 2–3 人日（字段/状态机/迁移脚本）+ 已有代码基本不动 | **CLI 子进程版 8–12 人日**；`import` 版 ≥15 人日且不稳（无公共 API，架构测试反向禁止） | **首版 5–7 人日**；硬化（契约测试、并发、降级、超时）约 2 周 |
| 依赖 | 0（stdlib + 现有 SQLite/JSON） | `pip install loopx`（**无 pip 依赖**）+ **系统 Node ≥ 22.22.3**（硬门槛，须在 PATH） | 同 B，但只在显式启用时要求；默认路径 0 依赖 |
| 行为保真度 | 中：语义对齐但**没有**真 LoopX 的 29 条 controller 规则、quota receipt、watch/monitor、跨 harness 续跑 | 高（就是 LoopX 本身），但**我们只能消费它的投影**，不能改 | 高（启用时）/ 中（默认时），按需切换 |
| 风险 | 与 LoopX 生态脱节；未来切 B 要二次迁移；容易"重新发明且语义漂移" | 版本漂移（1.x 契约仍在演进）、Node/Python 环境、双写/双权威、LoopX 快速迭代破坏兼容、Windows 路径与沙箱、进程管理 | 组合风险：两套状态并存 → **必须单写者纪律**；桥接层需长期维护；"两条 lane 的 evidence 一致性" |
| 兼容性 | 100%（现有 CLI/插件/看板不动） | 会与现有 `vue3migrate_core` CLI 冲突（同一 goal 两套 ID）；Hermes 插件工具需全部改写 | 兼容：保留现有工具，新增 `loopx_*` 命名空间；`backend` 是配置项 |
| 数据迁移 | 无需迁移 | SQLite/JSON → `.loopx/registry.json` + `ACTIVE_GOAL_STATE.md`（单向导出 + 人工校验；LoopX 无 bulk import API，需逐 goal `bootstrap/connect` + todo add） | 提供 `hermes-loopx export|import`（单向、幂等、可回滚），默认不自动迁移 |
| 适合场景 | 现在就要交付、离线/内网、单机批量 Vue 迁移 | 多 agent/多 harness 协作、需要真 quota/审核面、愿意吃 LoopX 版本 | **推荐**：现在用 A 保质交付；LoopX 就绪后按项目切换 |

### 6.3 推荐方案：C（混合），并给出落地设计

**为什么不是 A**：A 最大的坑不是工作量，而是**语义漂移**——LoopX 的 value 在于 `quota should-run` 的准入判断（QuietNoop / Repair / scope mismatch / await evidence）与 receipt 幂等，这些一旦"自研简化"，就退化成"带状态的定时器"，正是 README 说的 "Chat memory and a timer are not enough"。
**为什么不是 B**：B 把 Hermes 的差异化（Vue2→Vue3 领域包 + 质量门 + 看板）绑死在 LoopX 的迁移节奏上；且 LoopX 没有稳定 Python API，`import` 路径被其自身架构测试否定，只能走 CLI 子进程——那本质就是 C 的桥接层。
**为什么是 C**：C 把"语义对齐"（低成本、可立即做）和"真实后端"（可选、可降级）拆开，符合 LoopX 自己的 `host-integration-surface-v0` 设计哲学（thin hook + CLI fallback）。

**落地步骤（可执行）**

1. **插件骨架**：`E:\hermes\plugins\loopx_bridge\{plugin.yaml, __init__.py, bridge.py}`
   ```yaml
   name: loopx_bridge
   version: 0.1.0
   kind: standalone
   provides_tools: [loopx_status, loopx_should_run, loopx_todo_claim,
                    loopx_todo_update, loopx_refresh_state, loopx_spend_slot]
   provides_hooks: [pre_tool_call, pre_verify, on_session_end, subagent_start, subagent_stop]
   requires_env: []          # LoopX 可选；缺失时工具返回 unavailable 而非崩溃
   config_schema:
     backend: {type: string, enum: [sqlite, loopx], default: sqlite}
     registry_path: {type: string, default: ".loopx/registry.json"}
     loopx_bin: {type: string, default: "loopx"}
   ```
2. **桥接层**：`bridge.py` 统一 `run(argv: list[str], timeout=30)`：固定 argv、`--format json`、不拼 shell、`stderr` 只进日志、非零退出映射为结构化 `{ok: false, code, message}`（禁止裸异常进模型上下文）。
3. **等价性测试**：同一组 fixture（goal/todo/gate）在 sqlite 后端与 loopx 后端各跑 20 个用例，断言 `should_run` 布尔、`next_todo` 选择、`gate` 阻塞、`spend` 幂等；差异清单进 repo（这是 A↔B 切换的门禁）。
4. **单写者纪律**：一个 goal 同时只能一个后端写；切换需 `hermes loopx export → 人工确认 → 切换 → 只读校验`，禁止双写。
5. **钩子接线**：`pre_tool_call` 只做"是否允许受保护写"的判断（读 `should_run` 缓存 ≤ 1 turn）；`on_session_end` 只在有写发生时 `refresh-state`；`subagent_start` 注册 peer `agent_id`。
6. **可观测**：插件 `state` 记绑定表 `{session_id, thread_id, goal_id, agent_id, backend, last_receipt_id}`；CLI `hermes loopx doctor|status|bind`。

### 6.4 数据模型映射表（自研内核 ↔ LoopX）

| Hermes `vue3migrate_core` | LoopX 真实模型 | 映射规则 |
|---|---|---|
| `Goal(id,title,description,scope,quota_total,status)` | registry 条目 + `ACTIVE_GOAL_STATE.md` 的 objective/authority/guards | 导出时一个 Goal = 一个 registry goal；`scope` → `goal_boundary.write_scope`；不导出内部 ID 之外的私有路径 |
| `Todo(id,goal_id,file_path,phase,dependencies,max_attempts,status,owner_agent)` | Todo：`todo_id`、`task_class`、`claimed_by`、`write_scope`、acceptance/evidence、`blocks_agent` | `phase` → 领域 lane 标签（capability 投影）；`dependencies` → 后继 todo 的 `blocks` 关系；`max_attempts` 留在 Hermes（LoopX 用 replan/repair + quota，不用 attempt 计数） |
| `Gate(id,goal_id,scope,status)` | 用户 todo（`user_gate`）+ `operator-gate --decision` | 质量门（分数阈值）→ `user_action`（非阻塞）/ `user_gate`（阻塞）；阈值判定留在 Hermes |
| `Evidence(id,todo_id,agent_id,score,artifacts,notes)` | `todo complete --evidence "<public-safe>"` + run index 行 + `human_reward` overlay | **只写 public-safe 摘要**（分数、文件计数、校验命令、diff 摘要哈希）；原始日志/截图不进 LoopX |
| `Checkpoint(id,goal_id,todo_id,state)` | `refresh-state` + vision checkpoint + checkpointed boundary authority | 断点续跑语义不同：LoopX 靠 active state + run history + receipt 重放，不存任意 JSON blob |
| `Experience(category,trigger,solution,versions,times_hit)` | **无对应**（LoopX 的 Reward Memory 是实验性、default-off、provider-neutral） | 保留在 Hermes（这正是 Hermes 的差异化记忆层），不强行映射 |
| `quota_total/quota_used/spend_slot` | `quota should-run` + `spend-slot --slots 1 --source heartbeat --execute` | **语义不同**：Hermes 的 quota 是"重试/轮次预算"；LoopX 的 quota 是"是否允许自动继续 + 每次已验证交付记 1 格"。映射表必须写清，不要混用 |
| `ShouldRunResult(ok,reason)` | `interaction_contract.mode`（10+ 种）+ `next_cli_actions` | 不要压成 bool；至少要保留 `mode`、`primary_action`、`scheduler_hint` 三字段 |

---

## 7. 对 Vue2→Vue3 迁移场景的映射

| LoopX 原语 | 在 Vue2→Vue3 迁移中的含义 | 具体字段/落法 |
|---|---|---|
| **Goal** | 一个迁移项目（仓库 + 分支 + 验收基线），跨会话存活 | objective：「package.json 升 vue@3.x + vue-router@4 + pinia，构建与 e2e 全绿」；`goal_boundary.write_scope` = 允许改的目录；authority sources = 迁移规范 / 兼容性白名单 / 业务方确认 |
| **Todo** | 一个可独立验收的切片：组件 / 文件 / 模块 | 现状 `Todo.file_path + phase` 保留为领域字段；LoopX 侧补 `task_class`（`implementation` / `validation` / `user_gate`）、`write_scope`（该文件 + 其单测）、acceptance（build 通过 + 组件快照 diff 阈值） |
| **Gate** | 质量门（70/85 两档）+ 人工门 | 自动门：`quality_score < 阈值` → 自动回环（不是 gate）；跨语义边界（Vuex store 拆分、`filters`→`computed`、`v-model` 行为变化）→ `user_gate`，`blocks_agent=true` 只阻塞该 lane；`operator-gate --decision approve/reject/defer` 落账 |
| **Evidence** | build/test/browser 结果的可审计摘要 | `todo complete --evidence "vitest 42/42; vue-tsc 0 err; playwright 6/6; diff +128/-96"`；截图和原始日志放 Hermes 侧 `state/`，LoopX 只存指针 + 摘要（隐私边界） |
| **Quota** | 每次自动 turn 的算力配额（防"跑飞/烧钱"） | `quota should-run` 决定"要不要再自动跑一轮"；每次**已验证**交付后 `spend-slot --slots 1 --source heartbeat`；`scheduler_hint` 决定心跳节奏（不要用固定 cron 硬顶） |
| **Receipt / Turmidempotency** | 同一 turn 重试不重复扣配额、不重复写证据 | 用 `--turn-instance-id` 贯穿 `quota should-run` / `spend-slot`；Hermes cron 场景取 `ctx.current_cron_execution()` 生成稳定 id |
| **QuietNoop / Repair** | 迁移卡住时的正确姿势 | 没有可运行切片 → `monitor_quiet_skip`（不花配额、写 receipt）；状态漂移（文件已被别人改）→ `Repair`，先重建投影再干活——这比"重试 3 次再人工"更省注意力 |

**落地建议**：Vue 迁移的"串行硬约束"（一次只跑一个节点）在 LoopX 里天然成立（`(goal_id, todo_id)` 竞争单元 + lease），不需要自研全局锁；但**跨文件批量**时应拆成多个 todo 而不是拉长单 todo，否则 receipt/quota 粒度失真。

---

## 8. 风险与未决问题

### 8.1 风险

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | **LoopX 版本漂移**：1.x 仍在快速迭代；协议标注 v0；已有一次实验被 PR #5054 退休；CLI 参数可能随 minor 变化 | 桥接层随时失效 | pin 精确版本（`loopx==1.2.x` 起，按 dsh 插件同款版本下限）；启动时 `loopx doctor` + 版本闸门；JSON 解析全字段可选、未知字段 additive；CI 固定版本跑契约测试 |
| R2 | **双权威/双写** | 数据分叉、double spend | 单写者：`backend` 一次只一个；切换走 export→人工确认→import→只读校验；禁止后台同时写 |
| R3 | **Node 运行时是硬依赖**：Python 侧 `requires-python>=3.11`、`dependencies=[]`（Hermes 自带 Python 3.14.7 可用），但**控制面是 TypeScript**，必须有 **Node ≥ 22.22.3 在 PATH**；Hermes 自带 `E:\hermes\tools\node-26.7.0-win32-x64` 但未保证在 PATH | 桥接层全部 CLI 调用失败（`loopx` 起不来） | 启动探测 `loopx doctor` + `node --version`；必要时把 Hermes 的 node 目录注入子进程 `PATH`；`loopx_bin` 可配置；失败即降级到自研后端 |
| R4 | **进程与沙箱**：Hermes 插件在进程内，子进程受宿主沙箱/PATH/超时影响 | 工具卡死或报权限错 | 固定超时、`check_fn` 预检、失败返回结构化错误；Windows 上避免 shell=True |
| R5 | **License/合规**：Apache-2.0 + NOTICE 保留；衍生物不得冒充官方发布；不得以 AI 重写/改名规避归属 | 法务风险 | 不 fork、不复制内核代码（只走 CLI）；引用时保留 NOTICE 与链接；文档注明"集成方非官方" |
| R6 | **数据边界**：LoopX 的 todo/evidence 可能被其他 agent 写入，进入 Hermes 提示词即**不可信输入** | 提示注入、路径泄露 | 所有 LoopX 文本按数据渲染（不执行）；evidence 只接受 public-safe 文本；渲染前脱敏绝对路径/凭证 |
| R7 | **Windows 细节**：路径分隔、锁（`--registry` 相对路径按 registry 所在项目解析）、`msvcrt` 锁行为 | 状态写冲突 | 只用 LoopX 自己的锁语义；不要在插件里再加第二套锁；CI 覆盖 Windows |
| R8 | **README 的自证数据**：LHTB +17.3% / 200h 案例为项目自述，且明示"unequal budgets / 非独立因果估计" | 高估收益 | 不把 benchmark 数字作为选型主依据；以自身 Vue 迁移 A/B（有/无 LoopX 准入）度量 |

### 8.2 未决问题（需 lead/用户拍板）

1. **交付形态**：Hermes 插件是"新增 `loopx_bridge`"，还是把现有 `vue3_migration` 的 `backend` 扩一档（后者改动小但耦合）？
2. **是否需要 LoopX dashboard**：`loopx dashboard` 会起本地 web 服务，与 Hermes 自带看板并行是否可接受？（双 UI 成本）
3. **quota 语义冲突**：Hermes 现有 `quota_total/quota_used` 是"轮次预算"，LoopX quota 是"自动继续许可"。是改名（`max_attempts` vs `compute_quota`）还是保留两套字段？
4. **peer 协作范围**：是否真的要多 agent 共享同一 goal（LoopX 的强项）？若只是单机迁移，A 足够，B/C 的收益主要在"审核面 + 续跑"。
5. **LoopX 版本策略**：跟随 latest 还是 pin 到与 dsh-plugin 同款的 ≥1.2.4 并冻结？

---

## 附录 A：引用清单（URL 与本地文件行号）

### 外部（全部指向 HEAD `105c4bc` 所在的 main 分支）

| 引用 | 用途 |
|---|---|
| https://github.com/loopx-project/loopx | 仓库主页 |
| https://api.github.com/repos/loopx-project/loopx | stars/forks/license/语言/时间 ✅ |
| https://api.github.com/repos/loopx-project/loopx/commits?per_page=1 | HEAD sha `105c4bc…`、日期 ✅ |
| https://api.github.com/repos/loopx-project/loopx/contents/?ref=main | 根目录结构 ✅ |
| https://api.github.com/repos/loopx-project/loopx/contents/loopx?ref=main | `loopx/` 模块清单 ✅ |
| https://api.github.com/repos/loopx-project/loopx/contents/docs/reference/protocols?ref=main | 协议清单（turn-controller / host-integration / event-sourced 等）✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/README.md | 定位、宿主表、五问、CLI、License、benchmark ✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/docs/architecture.md | 六层、Turn 词汇、职责模型、依赖预算、lifetime goal ✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/docs/state-interaction-model.md | actor、存储、状态机、interaction modes、不变量 ✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/docs/reference/protocols/host-integration-surface-v0.md | 宿主接入契约、CLI fallback 命令、acceptance checks ✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/docs/reference/protocols/turn-controller-contract-v0.md | Turn 词汇/29 条规则/投影 ✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/docs/reference/protocols/event-sourced-state-contract-v0.md | JSONL 事件溯源已退休（PR #5054）✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/loopx/paths.py | `.loopx/registry.json`、`ACTIVE_GOAL_STATE.md`、`~/.loopx` ✅ |
| https://ghfast.top/https://raw.githubusercontent.com/loopx-project/loopx/main/pyproject.toml | `version=2.0.0a1`、`requires-python>=3.11`、`dependencies=[]`、Node 22.22.3 说明、`[project.scripts]`、package-data 中的 `.ts` ✅ |
| https://raw.githubusercontent.com/loopx-project/loopx/main/packages/dsh-loopx-plugin/README.md | 官方 DSH 插件边界、GoalBar、安装方式、`git+` URL 不可用 ✅ |
| https://ghproxy.net / https://gh-proxy.com / https://ghfast.top 镜像 | 直连 raw 被限流后的取文通道（内容与 raw 一致）|
| https://github.com/loopx-project/loopx/releases/tag/v1.4.2 | ⚠️ 版本号旁证（搜索结果） |
| https://zli12321.github.io/LHTB/index.html | ⚠️ 基准方页面（README 引用） |

### 本地（行号可核验）

| 文件:行 | 内容 |
|---|---|
| `E:\DHLocal\HERMES\vue3migrate-core\vue3migrate_core\adapters\loopx_adapter.py:1-11` | 设计目标与"对齐 domain-state"声明 |
| 同上 `:49-128` | 文件锁 + JSONL upsert 实现 |
| 同上 `:155-168` | `.loopx/domain-state/<goal>/<goal>.jsonl` 路径 |
| 同上 `:236-251` / `:253-281` / `:283-324` / `:326-350` / `:352-362` | 五原语实现 |
| 同上 `:470-504` | `LoopXBridge`（CLI 桥，参数不全） |
| 同上 `:510-522` | `create_kernel(backend)` 工厂 |
| `E:\DHLocal\HERMES\docs\PRD.md:423-427` | §12 集成方案 A/B 与"dsh plugin add"错误主张 |
| `E:\DHLocal\HERMES\docs\PRD.md:148-149` | FR-8 可插拔内核 |
| `E:\DHLocal\HERMES\README.md:291-306` | §8 内核切换表与五原语 |
| `E:\hermes\hermes-agent\hermes_cli\plugins.py:230` | `PluginContext` |
| 同上 `:456` / `:633` / `:933` / `:957` / `:853` / `:937` | register_tool / register_cli_command / register_hook / system_prompt_section / auxiliary_task / middleware |
| 同上 `:109-204` | `VALID_HOOKS` 全集（含 `pre_tool_call`、`pre_verify`、`on_session_end`、`subagent_start/stop`） |
| 同上 `:282` / `:386` / `:404` / `:409` / `:418` | `state` / `subagent_lifecycle` / `current_cron_execution` / `on_unload` / `spawn_task` |
| `E:\hermes\plugins\vue3_migration\plugin.yaml` | 现有插件 manifest（16 个 tools，`kind: standalone`） |
| `E:\hermes\plugins\vue3_migration\__init__.py:1-60` | 现有插件 `register` 前导与状态目录 |
| `E:\hermes\plugins\vue3_migration\vue3migrate_core\`（51 文件） | vendored 内核（含 `adapters/loopx_adapter.py` 22,080 B） |

## 附录 B：核验方法与局限

1. **未能 clone**：`git clone https://github.com/loopx-project/loopx` 在本机失败两次——schannel 报 `SEC_E_NO_CREDENTIALS`，改 `http.sslBackend=openssl` 后 `curl 28 Recv failure: Connection was reset`；`Invoke-WebRequest` 访问 `github.com` / `raw.githubusercontent.com` / `codeload` 均"接收时发生错误"。**本机直连 GitHub 被阻断，仅 harness 的 `web_fetch` 可出网**（后续经 `ghproxy.net` / `gh-proxy.com` / `ghfast.top` 镜像取到 raw 文本）。
2. 因此：**无本地源码副本**，无 `git log`/`git grep`，**无法给出行号**；所有仓库证据都是「commit `105c4bc` + 文件路径 + 章节名 / 原文引用」。`pyproject.toml` 已通过 `ghfast.top` 镜像**完整取到并核验**（✅ 版本/依赖/entry points/package-data）；仍有个别文档因 429 未取，已在对应处标注 ⚠️，未编造。
3. 已用 GitHub API 交叉核验：仓库元数据、HEAD、license、根目录结构、`loopx/` 与 `docs/reference/protocols/` 目录清单——目录/文件**存在性**是 API 级证据，**内容**是 raw 原文证据，两者分开表述。
4. 明确区分：**LoopX 真实能力**（有 CLI/文档/代码路径支撑）vs **前序产物自称**（§6.1 逐条标注）。未把前序产物当作 LoopX 事实来源。
5. 未执行任何 LoopX 安装/命令（本机无 LoopX，且不允许写工作区外），所有 CLI 行为来自官方文档与协议原文；`⚠️` 项（如 `v1.4.2`、`pyproject` 依赖、`loopx --help` 全量）明确标注未核验。
6. 安全：未打印任何密钥；引用的本地路径均为工程路径。
