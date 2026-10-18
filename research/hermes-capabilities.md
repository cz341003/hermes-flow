# Hermes Agent v0.22.2 能力侦察报告（证据化）

> 侦察对象：本机 `E:\hermes`（HERMES_HOME）与其源码仓库 `E:\hermes\hermes-agent`（v0.22.2，commit `d923a5e`，`install-stamp.json`）。
> 侦察方式：只读检查源码 / 官方文档 / 运行时日志 / 现有插件样例 `E:\hermes\plugins\vue3_migration`；未修改 `E:\hermes` 任何文件。
> 证据格式：`绝对路径:行号`。凡“未找到”的结论，均说明检索词。
>
> 时间基准：日志最后成功启动为 2026-10-18 11:01（`E:\hermes\logs\agent.log:638`），本报告成文于 2026-10-18 13:00 前后。

---

## 0. 结论摘要

用户 8 项需求按 Lead 侦察清单归并为下表（需求 9 = LoopX，单列在第 9 节；运行时健康单列第 10 节）。

| # | 需求 | Hermes 原生支持度 | 主要证据（file:line） | 插件需补什么 |
|---|---|---|---|---|
| 1 | 架构底座（agent loop / toolsets / sessions / gateway / 多端 UI / profiles） | **高** | `E:\hermes\hermes-agent\run_agent.py:214`（`class AIAgent`）、`agent\conversation_loop.py:1709`（`run_conversation`）、`tools\registry.py:427,666`（`ToolRegistry.register`）、`hermes_state.py`（SessionDB 家族）、`website\docs\developer-guide\architecture.md:13-49,141-174`、`user-guide\profiles.md:403-410` | 无需补；只需遵守插件契约（不在插件里猴补核心） |
| 2 | 插件化扩展（工具/命令/hook/provider/UI） | **高** | `hermes_cli\plugins.py:230`（`PluginContext`）、`:456`（`register_tool`）、`:933/937`（`register_hook/middleware`）、`:1020-1065`（12 类 provider 注册器）、`plugins_content.py:23,54`（`register_skill/register_automation_blueprint`）、`website\docs\developer-guide\plugins\index.md:734-743,1449-1559` | dashboard 若需可视化：必须自带预构建 `dashboard/dist/index.js` + `manifest.json` + `plugin_api.py`（`extending-the-dashboard.md:449-491,726-748`） |
| 3 | 技能体系（SKILL.md/发现/优先级/信任/自动加载） | **高** | `website\docs\user-guide\features\skills.md:194-229`（frontmatter）、`:406-428`（external_dirs 优先级）、`:467-519`（项目级技能 + trust）、`:172-192`（渐进披露 + 变更通知）、`agent\prompt_builder.py:1208,1581`（skills prompt snapshot） | 插件只能注册**只读**技能（`plugin:skill` 命名空间，`plugins_content.py:27-30`），不写进 `~/.hermes/skills/`；需要“专家技能包”时用 `ctx.register_skill()` |
| 4 | 自定义 Agent / 专家（角色 + 技能 + 调度） | **中** | `website\docs\user-guide\features\personality.md:9-41,159-171,212-230`（SOUL.md + /personality）、`profiles.md:403-410`、`features\delegation.md:9,34-78,329-342,532-550`（`delegate_task`）、`developer-guide\subagent-lifecycle-api.md:15-17,38-49`（`ctx.subagent_lifecycle`） | **无“专家注册表”**；需插件自建 roster（角色提示词 + 技能清单 + 工具白名单），再用 `delegate_task` / `subagent_lifecycle` 调度 |
| 5 | 工作流 / DAG / 编排 | **中** | `features\goals.md:7-9,136-154`（/goal + 质量门）、`features\loops.md:7-11,117-124`（/loop）、`features\kanban.md:97-140,716-736`（看板队列 + 依赖 + goal 卡）、`guides\automate-with-cron.md`、`plugin-catalog\hermes-workflows.yaml:4`（社区 DAG 插件；**核心无 DAG 引擎**，全仓 `dag` 仅在社区件描述里出现） | DAG 引擎需插件实现（先例：`vue3_migration` 自带 `Scheduler`）；核心可借用 kanban 做“持久队列 + 依赖 + 评审” |
| 6 | 记忆（结构化经验库 / 偏好 / 跨会话） | **高（基础）/ 中（结构化）** | `features\memory.md:11-20,36-57,235-260,544-546`（MEMORY.md/USER.md + session_search + provider 列表）、`developer-guide\memory-provider-plugin.md:87-215`（`MemoryProvider` ABC）、`features\memory-providers.md:30-45` | 经验库/踩坑沉淀：要么选 memory provider 插件（单实例，`memory.provider`），要么插件自建 SQLite（`plugins\plugin_storage.py` 的 `plugin_db()`） |
| 7 | 异常与恢复（重试/退避/断点/回滚/会话恢复） | **高** | `agent\error_classifier.py:34-66`（29 种 `FailoverReason`，覆盖 30+ 语义类别；QA 复核修正为 29）、`agent\retry_utils.py:30,121,155`（retry-after / 抖动退避 / 自适应限流）、`website\docs\user-guide\checkpoints-and-rollback.md:10-57`、`session-storage-recovery.md:8-23,62-81`、`developer-guide\state-db-recovery.md:20-57,76-85`、`user-guide\sessions.md:108-175` | 通用“工作流级 checkpoint + 续跑”核心没有；kanban 有崩溃回收（`kanban.md:138`），自研引擎需自持久化（`vue3_migration` 用 `workflow_checkpoint/restore`） |
| 8 | 质量门控 / 验证 | **中高** | `user-guide\features\hooks.md:459,823-848`（`pre_verify` 钩子）、`agent\verify\__init__.py:1-8` + `hermes_cli\subcommands\verify.py:19-45`（`hermes verify`）、`features\goals.md:136-154`（确定性 shell 质量门）、`features\kanban.md:48`（PR completion contracts）、`features\delegation.md:294-314`（`/review`）、`plugin-catalog\hermes-verifier.yaml:4`（社区 verifier） | 无“评分卡 + 测试门禁”框架；可用 `pre_verify` 钩子 + 自建 gate 工具补足（`hermes-verifier` 是社区参考） |

**一句话结论**：Hermes 原生给足了「底座 + 扩展点 + 持久化 + 恢复 + 调度原语」，但**没有**三样东西——①专家/Agent 注册表、②显式 DAG 工作流引擎、③通用质量门/评分卡框架。这三样正是「HERMES 迁移控制面插件」要补的核心，且已有 `vue3_migration` 作为可运行先例。

---

## 1. 架构总览

### 1.1 进程/入口拓扑

| 入口 | 源码 | 说明 |
|---|---|---|
| CLI | `E:\hermes\hermes-agent\cli.py`（`HermesCLI` 门面）、`hermes_cli\main.py:3508`（`main()`）、`:3309`（`plugin_parser`，`hermes plugins` 子命令树） | `hermes chat`、`-q/-z` 单发、`-p <profile>` |
| 网关 | `gateway\run.py`（`GatewayRunner` 门面）、`gateway\session.py`、`gateway\platforms\` | 常驻进程，25+ 平台适配器（内置 + `plugins/platforms/*`） |
| ACP | `acp_adapter\` | IDE（VS Code/Zed/JetBrains）stdio JSON-RPC |
| Web Dashboard | `hermes_cli\web_server.py`、`tui_gateway\server.py` | `hermes dashboard` / `hermes serve`；TUI 走同一 server 的 `/api/ws` |
| 桌面 | `apps\desktop\`（Electron）+ `hermes serve` 后端 | 与 dashboard 共享 `plugin_api.py` 后端命名空间 |
| 批处理/轨迹 | `batch_runner.py`、`trajectory_compressor.py` | 批量跑 prompt / 生成 ShareGPT 轨迹 |

证据：`website\docs\developer-guide\architecture.md:13-49`（五入口 → AIAgent 图）、`:53-137`（目录职责）、`:141-174`（CLI/Gateway/Cron 三条数据流）。

### 1.2 Agent Loop（核心调用链）

- 门面：`run_agent.py:214` `class AIAgent(...)` —— 明确注释为 facade，循环体在 `agent\conversation_loop.py`。
- 循环：`agent\conversation_loop.py:1709` `def run_conversation(...)`；每轮相位拆到 `agent\turn_*.py`（`turn_iteration_prep / turn_api_call / turn_api_error / turn_overflow / turn_truncation / turn_recovery`）。
- 工具执行：`agent\tool_executor.py`；`todo`/`memory`/`session_search`/`delegate_task` 四个“agent-level tool”在进 registry 之前被拦截（`architecture` 文档 `agent-loop.md:150-161`）。
- 注册表：`tools\registry.py:427` `class ToolRegistry`、`:666` `def register(...)`，工具文件 import 时自注册（`architecture.md:268-280`）。
- Prompt 组装：`agent\prompt_builder.py`（稳定层/上下文层/易变层），技能索引快照落盘 `<HERMES_HOME>\.skills_prompt_snapshot.json`（`agent\prompt_builder.py:1208-1209`、写入 `:1581`；本机该文件 45,122 B，mtime 2026-10-17 16:31）。
- 会话持久化：`hermes_state.py` + `hermes_state_*.py` 家族（SQLite + FTS5；`state.db`、`shared-state.db`、`projects.db` 在 `E:\hermes`）。

### 1.3 Toolsets（工具分组）

`toolsets.py` / `toolset_distributions.py`；文档 `reference\toolsets-reference.md`：
- 核心 toolset 表：`:51-88`（`file/terminal/browser/web/memory/skills/delegation/kanban/computer_use/code_execution/todo/session_search/...`）。
- 平台 toolset：`:90-120`（`hermes-cli` 默认全集；`hermes-acp`/`hermes-api-server` 收窄）。
- 动态 toolset：`:122-145`（MCP 生成 `mcp-<server>`；插件 `ctx.register_tool()` 生成新 toolset；`custom_toolsets`）。
- 关键约束：`kanban` **不被 `all/*` 打开**，必须显式列出（`:162-165`）。

### 1.4 Profiles / 多实例

- Profile = `HERMES_HOME` 边界：`hermes -p coder` 把 `HERMES_HOME` 指向 `~/.hermes/profiles/coder`，config/.env/sessions/memory/skills/state.db/gateway PID/logs/cron 全部隔离（`user-guide\profiles.md:403-410`）。
- 本机只有一个 home `E:\hermes`（无 `profiles\` 目录），即 default profile。

---

## 2. 插件系统 API 清单

### 2.1 载体与启用

| 项 | 事实 | 证据 |
|---|---|---|
| 三类发现源 | 用户 `$HERMES_HOME/plugins/`、项目 `.hermes/plugins/`、pip entry point `hermes_agent.plugins` | `architecture.md:233-237`；`plugins\index.md:2188-2204` |
| 目录结构 | `plugins/<name>/plugin.yaml` + `__init__.py`（`register(ctx)`）；可带 `skills/`、`dashboard/`、`desktop/`、`pyproject.toml`、`mcp.json` | `plugins\index.md:904-912,477-527` |
| 启用 | **opt-in**：`plugins.enabled` 白名单；`hermes plugins enable/disable/list/install/update/remove/doctor/validate/capabilities` | `features\plugins.md:150-199,398-420`；`plugins\index.md:249-267` |
| 本机实际启用 | `E:\hermes\config.yaml:63-74`：`plugins.clone_timeout_seconds` + `enabled: [vue3_migration]`、`disabled: []`；`:1158-1159` 把 `vue3_migration` 挂到 `hermes-cli`/`hermes-telegram` toolset | `E:\hermes\config.yaml:72-74,1158-1159` |
| 生效时机 | 插件在**进程启动时**由 `PluginManager.discover_and_load()` 加载（`hermes_cli\plugins.py:1279`）；中途装插件对 gateway 命令/hook 立即生效，对 `tools`/`prompt` 延到**下个会话**（`plugins\index.md:1779-1807`） | 同左 |
| 加载失败 | `register()` 异常只禁用该插件，Hermes 继续（`plugins\index.md:753`） | — |
| `kind` 取值 | `standalone`（通用插件，`features\plugins.md:141`；本机 `vue3_migration/plugin.yaml:5` 即 `kind: standalone`）、`backend`（`browser/web/image_gen/video_gen/terminal_env` 后端）、`platform`（网关适配器）、`model-provider`（`providers/` 生命周期，非 PluginManager 导入）、`exclusive`（memory provider 自动判定，走 `memory.provider`） | `features\plugins.md:141`；`plugins\index.md:902,1841-1845,1891-1906,1996-2002`；`model-provider-plugin.md:21` |

### 2.2 `register(ctx)` 可用 API（全部来自源码，行号为定义处）

`PluginContext` 定义在 `E:\hermes\hermes-agent\hermes_cli\plugins.py:230`。

| 方法 | 签名/关键参数 | 用途 | 证据 |
|---|---|---|---|
| `register_tool` | `(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, description="", emoji="", override=False)` | 注册工具；`override=True` 替换内置工具需 `capabilities: tools.override` + 运营方授权 | `plugins.py:455-498` |
| `register_cli_command` | `(name, help, setup_fn, handler_fn)` | `hermes <plugin> <sub>` 子命令树 | `plugins.py:633`；`plugins\index.md:1449-1483` |
| `register_command` | `(name, handler, description="", args_hint="")` | 会话内 `/name` 斜杠命令（CLI/gateway） | `plugins.py:647`；`plugins\index.md:1487-1536` |
| `register_hook` | `(hook_name: str, callback: Callable)` | 生命周期钩子（见 2.4） | `plugins.py:933` |
| `register_middleware` | `(kind: str, callback)`；kind ∈ `tool_request/llm_request/tool_execution/llm_execution` | 改写请求/包裹执行（比 hook 更强） | `plugins.py:937`；`plugins\index.md:1411-1447` |
| `register_context_engine` | `(engine: ContextEngine)` | 替换上下文压缩引擎（单例，`context.engine`） | `plugins.py:686`；`plugins\index.md:1950-1972` |
| `register_memory_provider` | `(provider: MemoryProvider)` | 外部记忆后端（单例，`memory.provider`） | `plugins.py:723`；`plugins\index.md:1910-1948` |
| `register_skill` | `(name, path, description="", frontmatter=None)` | 随插件发只读技能，`skill_view("<plugin>:<name>")` | `plugins_content.py:22-52` |
| `register_automation_blueprint` | `(key, *, title, description, schedule_template, prompt_template, category, slots, deliver_default, skills, tags)` | 往 `/blueprint` + dashboard 自动化画廊加模板 | `plugins_content.py:53-79` |
| `register_dashboard_auth_provider` | `(provider)` | dashboard OIDC/密码登录后端 | `plugins.py:735` |
| `register_platform` | `(name, label, adapter_factory, check_fn, required_env, env_enablement_fn, cron_deliver_env_var, emoji, platform_hint)` | 注册网关平台适配器 | `plugins.py:777` |
| `register_platform_handler` | `(platform, factory)` | 给某平台挂原生事件处理器（工厂 `(native, adapter)`） | `plugins.py:829` |
| `register_slack_action_handler` | `(action_id, callback)` | Slack Block Kit 按钮回调 | `plugins.py:810` |
| `register_approval_transport` | `(name, present_fn)` | 自定义人工审批通道 | `plugins.py:430` |
| `register_system_prompt_section` | 见源码 | 向 system prompt 注入稳定段落 | `plugins.py:957` |
| `register_auxiliary_task` | 见源码 | 注册 aux LLM 任务（结构化输出/标题等） | `plugins.py:853` |
| `register_locale` / `register_locale_dir` | `(id, yaml/mapping, endonym, surface)` | 语言包 | `plugins.py:890,915` |
| `register_cron_scheduler` | `(provider)` | 替换 cron 调度器（社区 chronos） | `E:\hermes\hermes-agent\plugins\cron_providers\__init__.py:100` |
| `register_computer_use_provider` | `(provider: ComputerUseProvider)` | 换 computer_use 驱动 | `E:\hermes\hermes-agent\plugins\computer_use\__init__.py:86` |
| `register_{image_gen,video_gen,web_search,browser,terminal_environment,secret_source,tts,transcription}_provider` | 见 `_SCOPED_PROVIDER_REGISTRARS` 表 | 各类后端注册（type-check + scope registry + unload 还原） | `plugins.py:1020-1065` |
| `dispatch_tool` | `(name, args, *, parent_agent=None) -> str` | 在插件里以父 agent 上下文调用任意工具（approval/预算走正常管道） | `plugins.py:674`；`plugins\index.md:1538-1575` |
| `has_capability` | `(capability) -> bool` | 探测授权（`tools.override` / `llm.*`） | `plugins.py:501-507` |
| `call_mcp` | `(server, tool, arguments, timeout=30)` | 复用 MCP 原生客户端 | `plugins.py:509` |
| `inject_message` | 见源码 | 向 gateway/TUI 会话注入一条消息 | `plugins.py:603` |
| `llm`（属性） | `PluginLlm`：`complete/complete_structured/acomplete/acomplete_structured` | 宿主持有凭据的 LLM 调用，`provider=/model=` 受能力门控 | `plugins.py:376-384`；`plugin-llm-access.md:9,209-245,393-470` |
| `subagent_lifecycle`（属性） | `SubagentLifecycleService`：`launch/wait/status/steer/cancel/result/reconnect` | 插件安全地派生/监督子代理 | `plugins.py:386-391`；`subagent-lifecycle-api.md:15-49` |
| `state`（属性） | `PluginState.get/set`（profile 级、原子、≤10 MiB） | 插件自有运行态 | `plugins.py:282-285`；`plugins\index.md:789-805` |
| `get_config/set_config` | `(key, default)` / `(key, value)` | 只读写 `plugins.entries.<id>.settings.*` | `plugins.py:266-280` |
| `on_unload` / `spawn_task` | `(callback)` / `(coro, name)` | 卸载清理 / 受监督 asyncio 任务 | `plugins.py:409-428` |
| `emit / subscribe` | `(event, payload)` / `(event, callback)` | 插件命名空间内事件总线 | `plugins.py:984-1011` |
| `profile_name` / `current_cron_execution()` | 属性/方法 | 在任意宿主进程里拿当前 profile / cron 运行身份 | `plugins.py:393-407` |
| 模块级持久化 | `plugin_data_dir(name)` / `plugin_db(name)` | `<home>/plugin-data/<name>/`、SQLite（WAL） | `plugins\plugin_storage.py`；`plugins\index.md:941-961` |

### 2.3 `plugin.yaml` 字段（v1 + v2）

v2 参考表：`plugins\index.md:429-467`。要点：
- v1：`name/version/description/author/provides_tools/provides_hooks/requires_env/python_dependencies/capabilities/requires_auth`。
- v2 增量：`manifest_version`、`api_version`、`requires_plugins`（拓扑排序加载）、`config_schema`（Desktop 设置表单）、`license/homepage/tags/provides_locales`。
- `provides_tools` 只影响 `validate`/目录展示/`needs auth` 提示，**不决定**用户插件工具是否加载（`plugins\index.md:286-291`）。
- 能力声明 `capabilities:`（`tools.override`、`llm.provider_override`、`llm.model_override` 等）走一次同意屏，**fail-closed**（`plugins\index.md:307-331`）。
- 本机样例 `E:\hermes\plugins\vue3_migration\plugin.yaml`：`kind: standalone`，`provides_tools` 16 项，`provides_hooks: []`。

### 2.4 Hook 清单（`register_hook` 可注册）

摘要表：`plugins\index.md:1272-1291`；详尽签名：`user-guide\features\hooks.md`。

- 控制型（返回值有意义）：`pre_tool_call`（可 `{"action":"block"|"approve"}`）、`pre_llm_call`（可 `{"context": "..."}` 注入本轮用户消息）、`pre_verify`（编辑代码后的验证门，可继续/阻断收尾）。
- 观察型：`post_tool_call`、`post_llm_call`、`pre/post_api_request`、`pre/post_auxiliary_call`、`on_session_start/end/finalize/reset`、`gateway_platform_event`、`kanban_task_claimed/completed/blocked`。
- 上下文注入上限 10,000 字符，超出写 `$HERMES_HOME/hook_outputs/...` 并给头尾预览（`plugins\index.md:1319-1331`）。

### 2.5 插件如何提供 Web / Dashboard UI（关键）

**Web dashboard（`hermes dashboard`）** 的插件契约（`user-guide\features\extending-the-dashboard.md`）：
- 目录：`~/.hermes/plugins/<name>/dashboard/{manifest.json,dist/index.js,plugin_api.py}`（`:427-449`）。
- `manifest.json` 字段：`name/label/description/icon/version/tab{path,position,override,hidden}/slots/entry/css/api`（`:449-491`）。
- 前端 SDK：`window.__HERMES_PLUGIN_SDK__` + `window.__HERMES_PLUGINS__.register(name, Component)` / `.registerSlot(name, slot, Component)`（`:495-562,828-833`）。
- 后端：`plugin_api.py` 导出模块级 `router = APIRouter()`，自动挂到 `/api/plugins/<name>/`（`:726-748`）；**新增/新启用插件由 hot-mount fallback 在首次请求时现场挂载**（`web_server_dashboard.py:899-973`），只有已挂载路由的代码变更才需重启 web server（日志证据：`E:\hermes\logs\agent.log:639-640`）。
- 发现：扫描 3 个目录，`GET /api/dashboard/plugins`、`GET /api/dashboard/plugins/rescan` 热重扫（`:807-833`）。
- 限制：dashboard 插件只能靠目录布局安装，pip 安装未接线（`:927`）。

**原生桌面（`hermes desktop`）** 是另一个 SDK：`$HERMES_HOME/desktop-plugins/<id>/plugin.js`（纯 ESM、无构建），贡献 panes / pages / sidebar / status bar / palette / keybinds / themes / settings pages；统一包放 `$HERMES_HOME/plugins/<id>/desktop/plugin.js`（`developer-guide\desktop-plugin-sdk.md:64-69,225-231,1656-1740`）。两边**只共享** `plugin_api.py` 后端命名空间（`extending-the-dashboard.md:20`）。

**本机已装 dashboard 插件先例**：`plugins\kanban\dashboard\manifest.json`（`tab.path=/kanban`、`entry: dist/index.js`、`api: plugin_api.py`）+ `plugin_api.py`（FastAPI router、WebSocket `/events`）。日志显示启动时挂载 `/api/plugins/kanban/`、`/api/plugins/hermes-achievements/`（`agent.log:639-640`）。

**缺口**：现有 `vue3_migration` 只做了 `board_render` → 生成 HTML 文件（`E:\hermes\plugins\vue3_migration\__init__.py:206-209,518`），**没有** `dashboard/manifest.json` 与预构建 JS bundle，因此不会出现在 dashboard 导航里。要“控制面 UI”必须补 `dashboard/` 三件套。

### 2.6 插件隔离/安全

- `plugins.isolation: host|subprocess`（`features\plugins.md:803-850`）；`hermes plugins doctor/validate` 静态扫描 + 临时 HERMES_HOME 试加载（`plugins\index.md:248-267`）。
- 安装/更新时静态安全扫描（`features\plugins.md:733-753`）。
- 插件契约：**不允许**猴补核心（`AIAgent.<method>`、`sys.modules`、core dict），catalog 准入直接拒（`plugins\index.md:187-194`）。

---

## 3. 技能系统

### 3.1 规范（SKILL.md frontmatter）

`user-guide\features\skills.md:194-229`：
```yaml
name, description, version, platforms: [macos|linux|windows]
metadata.hermes.tags / category
metadata.hermes.fallback_for_toolsets / requires_toolsets   # 条件激活
metadata.hermes.fallback_for_tools / requires_tools
metadata.hermes.config[]                                    # config.yaml 设置项
required_environment_variables[]                            # 加载时安全询问
```
目录结构：`skills/<category>/<name>/{SKILL.md,references,templates,scripts,examples,assets}`（`:335-358`）。

### 3.2 发现目录与优先级

**优先级（高→低）**：`project → local (~/.hermes/skills/) → skills.create_dir → external_dirs`（`skills.md:426,496-498`）。
- 项目级：`<project-root>/.hermes/skills/`、`<project-root>/.agents/skills/`，root = 最近的含 `.git` 祖先（`:467-476`）。
- 外部目录：`config.yaml → skills.external_dirs`（`:406-428`）。
- 重定向创建：`skills.create_dir`，且 agent 指令会跟随该配置动态渲染（`:448-464`）。
- bundled：`<repo>/skills/`（本机 `E:\hermes\hermes-agent\skills` 下 **58** 个 `SKILL.md`），optional 官方技能 153 个（`optional-skills/`），用户 home 内 **65** 个（实测 `Get-ChildItem E:\hermes\skills -Recurse -Filter SKILL.md` 计数）。
- 插件技能：`plugin:skill` 独立命名空间，只读，不进 `~/.hermes/skills/`（`plugins\index.md:996-1000`；`plugins_content.py:27-30`）。

### 3.3 trust 与安全

- 项目技能默认**不自动加载**：首次进 repo 提示 `hermes skills trust`，信任根写 `skills.trusted_project_dirs`（`skills.md:478-494`）。
- 扫描期隔离：项目技能每次内容变更用同一安全扫描器复核，`dangerous` 判决 → 隔离、不进索引、按名加载报错（`skills.md:511-513`）。
- Hub 安装：`skills/.hub/lock.json` 记录来源/哈希/扫描器版本；`quarantine/`、`audit.log`（`:353-365`）；trust levels（`:918-930`）。

### 3.4 自动加载机制

- **渐进披露**：`skills_list()`（~3k token 索引）→ `skill_view(name)`（全文）→ `skill_view(name, path)`（引用文件）（`skills.md:172-180`）。
- **系统提示索引快照**：`agent\prompt_builder.py:1208-1209` 读 `<HERMES_HOME>\.skills_prompt_snapshot.json`（本机 45 KB，`E:\hermes\.skills_prompt_snapshot.json`），`:1581` 原子写；会话中途增删技能只在下一条消息带一次“变更通知”，系统提示到下个压缩点才更新（`skills.md:184-192`）。
- **斜杠命令**：`/<skill-name>`；bundles 把多个技能绑一个命令（`skills.md:521-597`）。
- **自动创建与维护**：`skill_manage` 工具（create/patch/write_file/remove_file/delete，`:606-668`）；curator 后台做 `active→stale→archived`、可选 LLM 合并（`features\curator.md:9-13,38-44,60-64`）；`skills.write_approval` 门控写入（`:668-704`）。

### 3.5 技能与子代理/任务的绑定

- CLI：`hermes -s <skill>` 预载；cron job 的 `skills:` 列表把技能注入当次运行；kanban 卡支持 `--skills` 额外钉技能（`kanban.md:632`）。
- **`delegate_task` 没有 skills 参数**（`delegation.md:329-342` 只传 goal/context/images/output_schema）；子代理继承父的工具集，并自动带上 workspace 的 project context files（`.hermes.md`/AGENTS.md/CLAUDE.md/`.cursorrules`，**排除 SOUL.md**，`delegation.md:86`）。
- 结论：**“专家 = 角色提示词 + 技能清单”** 需要插件在派发时把技能内容写进 `goal/context`，或让子代理自己 `skill_view`；核心不提供“专家→技能”绑定。

---

## 4. Agent / 子代理与“专家定义”能力

### 4.1 有没有“Agent 注册表/专家机制”？

**没有**。检索词：`agent registry`、`agent type`、`expert`、`persona`、`role`、`soul`、`profiles`、`run_agent`、`agent/`。核心只有以下“人格/角色”相关面：

| 机制 | 作用域 | 证据 |
|---|---|---|
| `SOUL.md`（`$HERMES_HOME/SOUL.md`） | 实例级身份，system prompt slot #1，逐字注入（安全扫描 + 截断） | `personality.md:9-41,119-133` |
| `/personality <name>` | 会话级叠加，内置 14 种 + `config.yaml → agent.personalities` 自定义 | `personality.md:159-171,212-230` |
| Profile | 独立 HERMES_HOME（config/.env/sessions/memory/skills/state.db） | `profiles.md:403-410` |
| `AGENTS.md` / `.hermes.md` / `CLAUDE.md` | 项目级上下文（子代理也继承） | `features\context-files.md`；`delegation.md:86` |

本机 `E:\hermes\SOUL.md`（667 B）已存在，是当前实例人格。

### 4.2 子代理：`delegate_task`

- 工具：`tools\delegate_tool.py`；模型侧参数：`goal`、`context`、`images`（≤8）、`output_schema`（JSON Schema 校验 + 一次纠正轮）、`tasks[]` 批量、`background`；`role="orchestrator"` 可再派生（`delegation.md:34-125,532-576`）。
- 并发：默认 10 个（`delegation.max_concurrent_children` / `DELEGATION_MAX_CONCURRENT_CHILDREN`，无硬上限，超限报错）；`ThreadPoolExecutor` 执行（`delegation.md:211-217`）。
- 隔离：子代理上下文全新，只有 goal/context；**不能选择/扩大 toolset**（继承父）；leaf 子代理禁用 `delegate_task/clarify/memory/send_message/cronjob`，orchestrator 保留 `delegate_task`（`delegation.md:329-342,571-576`）。
- 预算：子代理迭代上限 `delegation.max_iterations`（默认 250）；父级 `agent.max_turns`（默认 500）（`delegation.md:342-352`；`agent-loop.md:180-186`）。
- 生命周期：`/agents`（别名 `/tasks`）TUI 面板、每个任务一份 append-only 日志、`steer` 干预（`delegation.md:433-532`）。

### 4.3 插件侧：`ctx.subagent_lifecycle`（推荐给控制面插件）

`subagent-lifecycle-api.md:15-49`：
- `SubagentLaunchRequest(goal, context, role, model, provider, allowed_toolsets, blocked_tools, working_directory, parent_session_id, correlation_id, metadata, timeout_seconds)`。
- `launch → handle`；`status/wait/cancel/steer/result/reconnect`；状态机 `PENDING/STARTING/RUNNING/SUCCEEDED/FAILED/INTERRUPTED/CANCEL_REQUESTED/CANCELLED/UNKNOWN`。
- 与 `delegate_task` 共用宿主侧构造/完成路径；结果 ≤32k 字符、不含 transcript/reasoning；进程重启后 `reconnect` 返回 `RECONNECT_UNAVAILABLE`。

### 4.4 多专家并发/串行调度：可用的四种原语

1. **单进程内并发**：`delegate_task(tasks=[...])` 批量 ≤10（可调）。
2. **跨进程并发**：kanban dispatcher 每 tick 按 board 扫描，为 card 派生 `hermes -p <profile> chat -q` 子进程；`max_concurrent`/失败熔断/崩溃回收（`kanban.md:138,1009-1025`）。
3. **串行硬约束**：kanban `task_links`（parents 全 done 才 promote `todo→ready`，`kanban.md:132`）；`/goal` 单会话串行（`goals.md:26-30`）。
4. **插件自研**：`vue3_migration` 自带 `Scheduler`（`E:\hermes\plugins\vue3_migration\vue3migrate_core\engine.py`，`cli.py:11-18` import `Edge/Node/Scheduler/Workflow`）。

**结论**：能通过“角色提示词 + 绑定技能”定义**逻辑专家**，但这是插件/调用方约定，不是 Hermes 的一等对象；多专家并发可借 `delegate_task` 或 kanban，串行/依赖可借 kanban link 或自研调度器。

---

## 5. 工作流 / 编排现状

| 机制 | 是什么 | 是否 DAG | 证据 |
|---|---|---|---|
| `/goal` | 「Ralph loop」：每轮后 aux 模型判定 `done/continue/blocked/wait`，未完成自动续跑；支持**completion contract**（outcome/verification/constraints/boundaries/stop_when）、`/subgoal`、**质量门（确定性 shell 命令，gate 先于 judge）**、waits、预算 `goals.max_turns=20`；状态存 `SessionDB.state_meta`，可 `/resume` | 否（单链循环） | `features\goals.md:7-9,42-73,81-154,217-223` |
| `/loop` | 会话内定时/自适应重跑 prompt 或 slash command；`--times`/`--until`/`LOOP_COMPLETE` 停止；`loops.max_ticks=100` | 否（定时器） | `features\loops.md:7-11,40-73,117-124` |
| cron | 真正的后台调度：jobs JSON、多 schedule、可挂 skills/scripts、投递到任意平台；gateway 内嵌 ticker | 否（任务表） | `developer-guide\architecture.md:165-174,239-243`；`guides\automate-with-cron.md`；`features\cron.md` |
| kanban | 多 agent 协作板：boards（各自 SQLite）、任务状态机（`triage|todo|ready|running|blocked|review|done|archived`）、`task_links` 依赖、comments 即协议、dispatch 子进程、`--goal` 卡、PR completion contracts、per-task model/skills、生命周期 hooks、dashboard 插件 | **部分**（只支持树/链式依赖，禁跨 board link；无 fan-out quorum） | `features\kanban.md:97-140,716-736,767-770`；`kanban_workflow.py:1-12`（只是列/移动矩阵，**不是引擎**） |
| todo | `todo_list` 工具，会话内清单 | 否 | `toolsets-reference.md:82` |
| blueprint | `/blueprint` 自动化模板（cron 的填表版） | 否 | `plugins\index.md:1635-1666` |
| `plugin-catalog\hermes-workflows.yaml` | **社区插件**（jacobhausler/hermes-workflows v1.3.6）：JSON DAG + 后台 runner + fan-out(quorum) + 人/机 gate + fingerprint replay-skip resume + steer + desktop DAG 视图 + 内联卡片；state 在 `$HERMES_HOME/workflows/` | **是** | `E:\hermes\hermes-agent\plugin-catalog\hermes-workflows.yaml:4`（长描述）、`:8` `requires_hermes ">=0.21.4"`、`:17-25` capabilities |
| `vue3_migration`（本机已装） | 自研控制面：`Workflow/Node/Edge/Scheduler` DAG + 串行硬约束 + checkpoint/restore + quality gate + recovery classify + experience base | **是** | `E:\hermes\plugins\vue3_migration\plugin.yaml`；`__init__.py:537-575` |

**核心引擎结论**：Hermes 核心**没有**通用 DAG/流水线引擎（检索词：`workflow`、`dag`、`pipeline`、`orchestrat`、`graph`；`hermes_cli/` 内唯一 `*workflow*` 文件是 `kanban_workflow.py`，自述为 board 列/移动矩阵，`kanban_workflow.py:1-12`）。DAG 要么装社区 `hermes-workflows`，要么自建（`vue3_migration` 已证明可行）。

---

## 6. 记忆能力

### 6.1 内置双层记忆

| 文件 | 内容 | 上限 | 证据 |
|---|---|---|---|
| `~/.hermes/memories/MEMORY.md` | agent 个人笔记（环境事实、约定、经验） | 2,200 字符 | `memory.md:11-20` |
| `~/.hermes/memories/USER.md` | 用户画像/偏好/沟通风格 | 1,375 字符 | 同上 |

- 注入方式：会话开始时**冻结快照**进 system prompt（带用量百分比），会话内写入立即落盘但 prompt 到下个会话才更新（`memory.md:36-57`）。
- 工具：`memory`（add/replace/remove，`memory`/`user` 两个 target；子串匹配；超限**报错不自动压缩**，agent 需自行腾挪）（`memory.md:90-205`）。
- 本机 `E:\hermes\memories\` 目录存在（待接管时注意 2,200/1,375 字符上限，不足以承载“结构化经验库”）。

### 6.2 跨会话检索

- SQLite + FTS5：`session_search` 工具查历史会话（`memory.md:235-260`）；库文件 `E:\hermes\state.db` + `state.db-wal`（FTS 表 `messages_fts*`）。
- 按 session/时间范围/`scroll` 翻页；`~20ms` FTS 查询（文档口径）。
- 会话搜索与记忆的分工表：`memory.md:250-260`。

### 6.3 外部记忆后端（memory provider）

- 单例选择：`memory.provider`（`config.yaml`）；ABC：`agent/memory_provider.py`，`plugins/memory/<name>/` + `register_memory_provider()`（`plugins\index.md:1910-1948`）。
- 必需方法：`name`、`is_available()`（禁网络）、`initialize(session_id, **kwargs)`、`get_tool_schemas()`、`handle_tool_call()`；配置 `get_config_schema/save_config`（`memory-provider-plugin.md:150-180`）。
- 可选钩子：`system_prompt_block`、`prefetch`（每轮 API 前召回）、`queue_prefetch`、`sync_turn`（每轮后持久化）、`on_session_end`、`on_pre_compress`（压缩前 fail-closed checkpoint）、`on_memory_write`（镜像内置写入）、`shutdown`（`:169-180,216-234`）。
- 内置/目录提供者：RetainDB、ByteRover（内置）；Honcho、Hindsight、Supermemory、Mem0、OpenViking、Holographic 等从 plugin catalog 装（`memory.md:544-546`；`memory-providers.md:45-66`）。
- 上下文引擎另有一条：`context.engine` + `ContextEngine`（`compression/update_from_response/should_compress/compress`），单例（`plugins\index.md:1950-1972`）。

### 6.4 能否支撑“结构化经验库 / 踩坑沉淀 / 用户偏好”

- **用户偏好**：原生够用（`USER.md` + `memory` 工具 + `pre_llm_call` 注入）。
- **踩坑沉淀**：原生 `MEMORY.md` 只 2,200 字符且纯文本；要么换 memory provider，要么插件自建库。先例：`vue3_migration` 用 `state/experience.db`（77,824 B，mtime 2026-10-17 20:18）+ `experience_add/experience_search` 工具（`plugin.yaml` + `state/`）。
- **闭环学习**：`/learn` 从来源学技能（`skills.md:117-170`）、`curator` 维护技能生命周期、`memory.md:263-283` 的 `/journey` 学习图谱、`agent/learning_graph*.py`。

---

## 7. 异常与恢复能力

### 7.1 错误分类与重试/退避

- `agent\error_classifier.py:34-66`：`FailoverReason` 枚举 **29 种**（覆盖 30+ 语义类别；`rate_limit`、`upstream_rate_limit`、`server_error`、`timeout`、`auth`、`billing`、`context_overflow`、`image_too_large/corrupt`、`content_policy_blocked`、`format_error`、`role_alternation`、`reasoning_mandatory`、`invalid_encrypted_content`、`llama_cpp_grammar_pattern`、`unknown` …），每种带恢复提示（retry / rotate credential / fallback / compress / abort），retry loop 直接用提示而非重新匹配字符串（`:4-5,70-90`）。
- `agent\retry_utils.py`：`parse_retry_after_seconds:30`、`jittered_backoff:121`（base 5s / max 120s / jitter 0.5）、`adaptive_rate_limit_backoff:155`、`reset_delay_from_message:110`、`format_reset_window:104`。
- 模型 fallback：`fallback_providers` 链；429/5xx/401/403 依序 fallback，401/403 先尝试刷新凭据（`agent-loop.md:188-198`）。
- 迭代预算：`IterationBudget`（父 500 / 子 250），用尽返回工作总结（`agent-loop.md:180-186`）。

### 7.2 截断 / 溢出

- 预压缩：>50% 上下文窗口触发；gateway 自动压缩 >85%（`agent-loop.md:200-213`）。
- 压缩保留最近 N 条（`compression.protect_last_n`，默认 20），tool_call/result 成对不拆，生成子会话 lineage（同上）。
- 输出上限重试（`max_tokens` 触发路径，`error_classifier.py:250` 注释）；`turn_overflow.py` / `turn_truncation.py` 专项相位。

### 7.3 Checkpoint 与回滚

- 影子 git 仓库 `~/.hermes/checkpoints/store/`，写文件/破坏性终端命令前自动快照；`/rollback [N] [--all] [diff]`、`/rollback <N> <file>`；`hermes checkpoints status/prune/clear`；默认**关闭**，`checkpoints.enabled` 或 `--checkpoints` 开启（`checkpoints-and-rollback.md:10-57,86-111`）。
- 触发清单：`write_file`/`patch`、`rm/rmdir/cp/install/mv/sed -i/truncate/dd/shred/>`、`git reset/clean/checkout`（`:29-34`）。

### 7.4 会话恢复 / 断点续跑

- CLI：`-c`（终端感知面包屑 `~/.hermes/terminal-sessions/`）、`--resume <id|title|latest>`、`--resume @claude|@codex` 导入、`--in <dir>`（`sessions.md:108-185`）。
- `/resume` 在 CLI/TUI/Desktop/gateway 通用；跨平台 handoff（`:225-265`）。
- goal/loop 状态持久化在 `SessionDB.state_meta`，压缩与 `/resume` 后仍存活（`goals.md:217-223`；`loops.md:99`）。

### 7.5 存储损坏恢复（state.db / WAL）

- FTS 损坏：置 `fts_stale`、拆 sync 触发器、走 `LIKE` 回退、不在写路径跑 rebuild（`state-db-recovery.md:20-33`）。
- 文件损坏：`StateDbCorruptError` 隔离 handle，停止一切写入、跳过 close checkpoint（保 `-wal` 取证）（`:35-57`）。
- 修复命令：`hermes sessions recover --source ... --inspect-only`、`hermes sessions repair [--check-only]`；`state-snapshots/` 快照回滚；`hermes doctor` 报 holder（`state-db-recovery.md:76-111`；`session-storage-recovery.md:23-81,93-107`）。
- WAL 互斥：另一进程持旧 WAL 时**拒绝写入**而非冒险；`sessions optimize/optimize-storage/prune` 在有 live writer 时拒绝（`session-storage-recovery.md:13-21,62-77`）。

### 7.6 任务级恢复

- kanban：dispatcher 每 tick 回收 stale claim、回收崩溃 worker（PID + 启动时间指纹）、超限自动 block（`kanban.md:138`）；block→unblock→re-run 是正式流程（`:104-110`）。
- 通用“工作流断点续跑”：核心**没有**；`hermes-workflows` 用 fingerprint replay-skip（社区件），`vue3_migration` 用 `workflow_checkpoint/restore`。

---

## 8. 质量验证能力

| 能力 | 细节 | 证据 |
|---|---|---|
| `pre_verify` 钩子 | 在 agent 准备收尾、且本轮编辑过代码时触发（仅在至少注册一个 hook 时）；返回 continue/block-stop 指令；`max_verify_nudges` 默认 3 | `user-guide\features\hooks.md:459,823-848`；`configuration.md:1265-1273` |
| evidence-based verify-on-stop | agent 编辑代码后若无“新鲜验证证据”会被内置 nudge 继续；`agent.verify_guidance` 控制文案 | `hooks.md:823-827` |
| `hermes verify` | 探测项目 recipe（bootstrap→build→test→start 后台→readiness 轮询→teardown）；`--detect-only/--save/--phase/--port/--timeout/--ready-timeout/--json`；manifest 落 `.hermes/environment.json`；已实测在 `main.py` 中接线（`build_verify_parser` 注册于 `subparsers`） | `agent\verify\__init__.py:1-8`；`agent\verify\runner.py:1-10`；`hermes_cli\subcommands\verify.py:19-45`；`hermes_cli\main.py:365,2183,3412` |
| `/goal` 质量门 | 确定性 shell 命令必须 exit 0 才允许 judge 判 done；失败输出尾部进续跑提示；默认 3 retries / 5 min 超时，耗尽自动 pause | `features\goals.md:136-154` |
| kanban 评审门 | `kanban_request_review` / `kanban_request_changes` / `review_dispatch`；review handoff 工件 staging；PR completion contracts | `features\kanban.md:48,716-736`；`toolsets-reference.md:72` |
| `/review` | 评审子代理（同 delegate_task 后台轨，拥有完整工具），读 PR/diff/跑代码 | `features\delegation.md:294-314` |
| 浏览器 E2E | 10 个核心 browser 工具 + `browser_exec`（browser-use 引擎，默认）+ CDP（`browser_cdp/browser_dialog`，需 `/browser connect` 或 `cdp_url`）+ 多后端（Browserbase/Browser Use/Firecrawl/Camofox/Lightpanda）+ `session=<name>` 并发隔离 | `features\browser.md:10-18,72-92,513-580,651-820`；`toolsets-reference.md:55` |
| computer_use | 通过 `cua-driver` 后台驱动桌面（不抢焦点）；权限模式 `standard/bounded/unrestricted`；危险动作走同一审批门；Windows/macOS/Linux | `features\computer-use.md:19-23,117-127,368-390` |
| 内置 evals | 仓库 `evals/` 下大量运行时用例（`browser_use/`、`compaction/`、`codex_echo/`、`core_tool_deferral/` …），面向工程回归，不是用户评分卡 | `E:\hermes\hermes-agent\evals\` |
| 社区 verifier | `hermes-verifier` v0.4.1：独立 verifier/advisor 模型逐轮评审、`note/caution/blocker`、可把 blocker 注入会话、`VERIFIER.yml` 多专家 roster、`VERIFIER.md` 优先级、`/verify` 命令 + dashboard API + Desktop 页；默认关闭 | `plugin-catalog\hermes-verifier.yaml:4,13` |

**缺口**：没有统一的“评分卡 + 测试执行 + 门禁放行”内建框架；需要 `pre_verify` 钩子 + 自研 gate 工具（或 `hermes-verifier`）。

---

## 9. LoopX 相关现状

- **检索结果：未找到**。检索词 `loopx` / `LoopX` / `LOOPX` 覆盖：`E:\hermes\hermes-agent` 全仓（含 `website/docs`、`plugin-catalog`、全部 `.py`）、日志、`config.yaml`、`E:\hermes\plugins` —— **0 命中**。
- 与“循环/自动续跑”语义最接近的原生能力：
  - `/loop`：会话内定时/自节奏重跑（`loops.md:7-11`，`/proactive` 别名）。
  - `/goal`：judge 驱动的 Ralph loop（`goals.md:7-11`，文档明确致敬 Codex CLI `/goal` 与 Ralph 模式）。
  - `hermes-workflows`（catalog 社区件）：DAG + fingerprint resume + gate，是“LoopX 式工作流”的最接近现成实现（`plugin-catalog\hermes-workflows.yaml:4`）。
- `plugin-catalog\hermes-workflows.yaml` **确与工作流强相关**：它是“Agent-owned workflow graphs”插件条目（JSON DAG、fan-out quorum、human/machine gate、backend runner 独立进程、Desktop DAG 视图、`::workflow{id}` 卡片），`requires_hermes >=0.21.4`（`:8`）。
- 结论：**Hermes 官方核心没有 LoopX 集成**；若 LoopX 是外部系统/协议，需自研插件桥接（当前无任何现成条目）。

---

## 10. 运行时健康状况与修复建议

### 10.1 入口脚本

`E:\hermes\bin\hermes.cmd` 第 3 行硬编码：
```
"E:\hermes\tools\python-3.14.7+20260901-win32-x64\python.exe" -I -c "import base64; exec(base64.b64decode('...'))" %*
```
`E:\hermes\bin\hermes-acp.cmd` 同样硬编码该路径。逻辑（base64 内嵌）是：设 `HERMES_HOME`、把 `E:\hermes\hermes-agent` 插入 `sys.path`、执行 `hermes_cli.main.main` / `acp_adapter.entry.main`。

### 10.2 实测故障链（证据）

1. `E:\hermes\tools\python-3.14.7+20260901-win32-x64` 目录存在（`Get-Item` 可读元数据，mtime 2026-10-17 15:43），但：
   - `Test-Path ...\python.exe` → `Access is denied`（不是 `False`）；
   - `Get-Item python.exe` → `UnauthorizedAccessException: Access is denied`；
   - `[System.IO.Directory]::GetFiles(dir)` → 访问被拒绝；`cmd dir` → `File Not Found`（0 项）；
   - `icacls` / `Get-Acl` 对该目录 → `Access is denied` / 未授权。
   - 同级 `tools\uv-0.12.3-win32-x64`、`tools\node-26.7.0-win32-x64` 同样**目录内容不可见/不可执行**。
2. 直接执行 `...\python.exe` → PowerShell「无法将 ... 识别为 cmdlet/可运行程序」（即 CreateProcess 失败）。
3. PM 环境 venv：`E:\hermes\installs\9249f73cb9b5d199\environments\8f5ab67cf9b943cd9a45aac0f3af4e1a\venv\pyvenv.cfg` 里 `home = E:\hermes\tools\python-3.14.7+20260901-win32-x64`；执行该 venv 的 `Scripts\python.exe` → 报
   `did not find executable at 'E:\hermes\tools\python-3.14.7+20260901-win32-x64\python.exe'`。
   → **基础解释器不可用 = venv 不可用 = `hermes` 全入口不可用**（`E:\hermes\installs\f0b915f54a5dedcc\...\python.exe` 同报错）。
4. 时间线旁证：`E:\hermes\.hermes-update-in-progress.lock`（0 B，mtime 2026-10-17 16:17）；`E:\hermes\tools\.reclaim-312650f856dc4d049fe402d5e19a9b2c`（回收标记）；`E:\hermes\logs\update_receipts\latest.json` 显示 2026-10-17T09:45Z 一次 `kind: sync` 且 `outcome: ok`、`venv_rebuild.ok=true`（但事后 tools/python 丢失，说明有中断/清理竞态）。
5. `E:\hermes\logs\tui_gateway_crash.log` 记录 2026-10-17 16:38–16:48 期间 gateway 子进程使用的正是该 python 路径，随后 `EPIPE` / 退出码 `3221225786`（0xC000013A，Ctrl+C/中断）。

### 10.3 关键反证：Hermes 曾经跑起来（插件系统本身没坏）

`E:\hermes\logs\agent.log`：
- `:457,486,516,546,575,604,638` → `Plugin discovery complete: 56 found, 52 enabled`（10-17 17:45 起至 10-18 11:01）；
- `:637` → `capability_check plugin=vue3_migration capability=tools.override decision=deny ... evidence=not granted`（插件注册代码被执行过）；
- `:639-640` → `Mounted plugin API routes: /api/plugins/hermes-achievements/`、`/api/plugins/kanban/`（dashboard 插件后端挂载成功）。
- 用户 `vue3_migration` 的运行产物仍在：`E:\hermes\plugins\vue3_migration\state\experience.db`（77,824 B，10-17 20:18）、`state\workflows.json`（10-17 19:46）。

→ **结论**：`plugins.enabled`、插件清单/代码、dashboard 后端挂载机制均正常；**当前唯一障碍是解释器（tools/python）不可用**。因此“插件在当前状态下能否加载”的答案是：**静态可加载、运行时不能加载**；解释器一恢复即可（有 52/56 成功记录）。

### 10.4 可用替代解释器（已实测）

`E:\hermes\installs\9249f73cb9b5d199\pm-runtime\generations\08c2ecb7c45c4c4e96e026b29d30c0bb\Scripts\python.exe`：
- `-V` → `Python 3.14.7`（可用）；
- 配合 `PYTHONPATH=E:\hermes\hermes-agent` 执行 `import hermes_constants; get_hermes_home()` → 输出 `E:\hermes`（**已实测成功**）。

说明：PM 的 pm-runtime 是独立自举的 uv CPython（其 `pyvenv.cfg home` 指向 `C:\Users\cz341\AppData\Roaming\uv\python\cpython-3.14-windows-x86_64-none`），不依赖 `tools\python`；但**它没有 Hermes 依赖**。Hermes 依赖在 `installs\...\environments\...\venv\Lib\site-packages`（含 `__editable__.hermes_agent-0.0.0.pth`），该 venv 的启动器坏了，只能靠“pm-runtime python + PYTHONPATH/site-packages”组合绕行。

### 10.5 修复建议（不动 `E:\hermes` 的前提下排序）

| 优先级 | 方案 | 说明 |
|---|---|---|
| P0 | **重跑官方安装器的运行时步骤** | `E:\hermes\hermes-agent\setup-hermes.ps1 -RuntimeOnly`：脚本先下载 uv（`setup-hermes.ps1:55`），再 `uv python install` + `python -m pm.cli install --runtime-only`（`:80-101`），正好重建 `tools\python` 与依赖，不需要手工删目录。 |
| P1 | 官方更新/修复入口 | 有可用解释器后 `hermes update`（self-update，`install-stamp.json:updateMechanism=self`）；或 `hermes pm install` 重装工具链（`setup-hermes.ps1:152` 提示）。 |
| P2 | 临时绕过（只读验证可行，不建议长期） | 用 10.4 的 pm-runtime python：`set HERMES_HOME=E:\hermes` + `PYTHONPATH=E:\hermes\hermes-agent;<venv>\Lib\site-packages`，再 `-c "from hermes_cli.main import main; main()"`；注意这绕过 `hermes.cmd` 的 `-I` 隔离，可能引入 cwd/PYTHONPATH 干扰。 |
| P3 | 排查“为何被回收” | 检查杀软/清理工具是否隔离了 `tools\*`；确认没有第二个 updater 在跑（`.hermes-update-in-progress.lock` 是 0 字节的陈旧锁，`update_receipts/latest.json` 已 ok）；修复后可删除陈旧锁（需写权限，本会话禁止）。 |
| P4 | 装完后的自检顺序 | `hermes doctor` → `hermes plugins list`（应见 `vue3_migration` enabled）→ `hermes plugins doctor vue3_migration --ci` → `hermes dashboard` 看 `/api/plugins/...` 挂载。 |

> 注意：本会话对 `E:\hermes` **只读**，以上均未执行；`E:\hermes\tools` 的 ACL 拒绝是“解释器不可用”的表现之一，但 `venv` 的 `did not find executable` 已独立证明基础解释器确实缺失/不可执行。

---

## 11. 对「HERMES 迁移控制面插件」的设计启示与缺口清单

### 11.1 可直接复用的原生能力（不要重造）

1. **工具 = 控制面动词**：每个控制面动作注册为 `ctx.register_tool(...)`，自动获得 schema→LLM 可见、approval、预算、hook 观测（`plugins.py:455-498`）。
2. **状态持久化**：`plugin_data_dir()`/`plugin_db()`（WAL SQLite）或 `ctx.state`（≤10 MiB JSON）；**别写插件安装目录**（`plugins\index.md:941-961`）。
3. **可视化**：`dashboard/manifest.json` + 预构建 `dist/index.js`（IIFE，调用 `window.__HERMES_PLUGINS__.register`）+ `dashboard/plugin_api.py`（FastAPI `router`，挂 `/api/plugins/<name>/`，可开 WebSocket）。参考 `plugins\kanban\dashboard\`。
4. **人机协同**：`ctx.register_command`（会话内 `/xxx`）、`register_approval_transport`（审批通道）、`inject_message`（异步回报）、`register_automation_blueprint`（cron 模板）。
5. **专家调度**：`ctx.subagent_lifecycle`（launch/wait/steer/cancel，最安全）或直接 `ctx.dispatch_tool("delegate_task", {...})`；并发上限由 `delegation.max_concurrent_children` 决定（默认 10）。
6. **经验注入**：`pre_llm_call` 返回 `{"context": ...}`（每轮注入、prompt 缓存友好、上限 10k 字符，`plugins\index.md:1300-1339`）；或实现 memory provider。
7. **质量门**：`pre_verify` 钩子 + 自研 `quality_gate` 工具；`pre_tool_call` 可 `block/approve`。
8. **观测/审计**：`post_tool_call`、`kanban_task_*`、`pre/post_api_request`、`ctx.emit/subscribe`、`ctx.llm` 的结构化输出。

### 11.2 核心缺口（插件必须自建）

| 缺口 | 现状 | 建议 |
|---|---|---|
| **专家注册表 / Agent 类型** | 无（只有 SOUL/personality/profile/skills） | 插件自带 `experts.yaml`（角色提示词 + 技能清单 + 允许 toolset + 模型），用 `subagent_lifecycle` 落成子代理；把角色提示词塞进 `goal/context`，技能用 `register_skill` 或让子代理 `skill_view` |
| **显式 DAG / pipeline 引擎** | 无（`/goal` 单链、kanban 树状、`/loop` 定时） | 插件内建 `Scheduler`（先例 `vue3_migration/vue3migrate_core/engine.py`），或依赖社区 `hermes-workflows`（注意其 runner 独立进程、gate 走 `wait.until_argv` 的披露风险，`plugin-catalog\hermes-workflows.yaml:4`） |
| **工作流级 checkpoint / 断点续跑** | 核心只有文件级 `/rollback` 与会话级 `--resume` | 插件自持久化（SQLite/JSON）+ 恢复工具；对齐 `error_classifier` 的 `FailoverReason` 语义做分类重试 |
| **结构化经验库** | `MEMORY.md` 2.2k 字符纯文本；session_search 只读历史 | 插件 `plugin_db()` 建经验表 + `experience_search` 工具；或做 memory provider（但单实例，会顶掉现有 provider） |
| **质量评分卡 / 测试门禁框架** | 只有 `pre_verify` 钩子、`hermes verify`、`/goal gate`、kanban review | 插件提供 `quality_score`/`quality_gate` 工具 + `pre_verify` 钩子；报告落库供 dashboard 展示 |
| **控制面 dashboard UI** | 现有插件只有 HTML 文件渲染 | 必须补 `dashboard/manifest.json` + 预构建 JS bundle + `plugin_api.py`；**后端路由需重启 web server 才挂载**（`agent.log:639-640`），前端可用 `/api/dashboard/plugins/rescan` 重扫 |
| **权限/同意** | `capabilities:` 一次性同意；`tools.override` 未授权即被拒（本机日志 `agent.log:637`） | 若需替换内置工具，必须在 `plugin.yaml` 声明 `tools.override` 并让用户同意；否则用非冲突命名 |
| **跨端（Desktop）** | Desktop 是另一套 SDK（`desktop/plugin.js`） | 控制面若要在桌面内嵌页面，需再写 `desktop/plugin.js`（纯 ESM、无构建）；否则用 Web dashboard |

### 11.3 对本机 `vue3_migration` 的评估（作为先例）

- **已具备**：`kind: standalone` + 16 工具（workflow_create/claim/complete/fail/run/status/delegate、quality_score/gate、recovery_classify、workflow_checkpoint/restore、experience_add/search、board_render）+ `register_cli_command`（`hermes vue3migrate`）+ DAG 引擎 + 经验 SQLite + 状态。
- **缺失**：`dashboard/`（无 manifest/JS bundle，只有 `board_render` 生成 HTML）；`provides_hooks` 为空（未用 `pre_verify`/`pre_tool_call`/`pre_llm_call`）；`capabilities.tools.override` 未授予（日志 `agent.log:637` deny，本机 `config.yaml:72-74` 只 enable 未授权）。
- **结论**：它是一个“控制面内核”原型；要成为真正的控制面产品，需补 **dashboard UI + hook 集成 + 能力声明/同意流程 + 技能包（`register_skill`）**。

### 11.4 证据可信度说明

- 文档行号来自 `E:\hermes\hermes-agent\website\docs`（v0.22.2 自带文档，与源码同 commit）。
- 源码行号来自 `E:\hermes\hermes-agent` 实际文件；`grep`/`read` 定位。
- “未找到”项：`loopx`（全仓 0 命中）、`agent registry`/`expert registry`/`agent type`（无对应模块）、核心 DAG（`hermes_cli/*workflow*` 仅 `kanban_workflow.py`，自述非引擎）、`hermes evals` CLI（`evals/` 只是工程用例目录）。
- 本报告**未**打印 `.env`/`config.yaml`/`auth.json` 中的任何密钥；`config.yaml` 仅引用非敏感键名与行号。
