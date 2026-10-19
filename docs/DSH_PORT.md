# HERMES Flow 迁移到 DeepSeek Harness（DSH）的可行性评估

- 日期：2026-10-19
- 结论：**可以实现，但不能直接安装现有 Hermes 插件**；需要 DSH 适配层。
- 当前产物：Hermes Agent Python 插件（`plugin.yaml` + `register(ctx)`），DSH 是 Cordis/TypeScript 插件体系。

---

## 1. 为什么不能直接复用

| 能力 | 当前 Hermes 实现 | DSH 要求 |
|---|---|---|
| 插件入口 | `plugin.yaml` + `register(ctx)` | npm 包 + `apply(ctx)` / `cordis.patch.yml` |
| 工具注册 | `ctx.register_tool(...)` | `inject: ['tools']` + `ctx.tools.register(defineTool(...))` |
| 工具返回 | JSON 字符串 `{ok,data}` | 唯一 canonical 值 + `output.schema` / `output.render` |
| 子代理 | `ctx.subagent_lifecycle.launch/wait/result` | DSH 的 subagent / Agent Teams 接口（需适配） |
| 上下文注入 | `pre_llm_call` hook | DSH hook/extension 点 |
| Dashboard | Hermes Dashboard SDK（`__HERMES_PLUGIN_SDK__`） | DSH client plugin（`dsh.client`） |
| CLI | `hermes flow` | 可独立运行，DSH 通过终端调用 |

**不能**把 `E:\hermes\plugins\hermes_flow` 直接复制到 DSH 插件目录。

---

## 2. 可复用的核心

`flow_core/` 基本与宿主无关（Python 标准库 + SQLite）：

| 模块 | 可复用度 |
|---|---|
| 专家/技能/工作流 registry | 高 |
| DAG / 批次规划 / 队列 / lease / split / repair | 高 |
| `WorkspaceAudit` 基线/回滚 | 高 |
| 质量采集（build/typecheck/Chrome CDP） | 高 |
| 经验库 / LoopX JSONL kernel | 高 |
| 异步质量 job manager | 高 |
| CLI（`flow_core`） | 高 |
| `flow_batch_auto` 的 **subagent launcher** | 低，需 DSH 适配 |
| Dashboard UI | 低，需重写为 DSH client plugin |
| `pre_llm_call` 记忆注入 | 低，需 DSH hook |

结论：**状态/批次/质量/审计可复用约 80–90%；真正要重写的是宿主适配层和 UI。**

---

## 3. 三条落地路线

### A. DSH Skill + CLI 桥（最快，0.5–1 天）

- 做一个 DSH skill，教模型调用：
  - `hermes flow status/plan-batch/verify`
  - 真实迁移时调用 `hermes chat --oneshot` 执行 `flow_batch_auto`
- 优点：几乎不改代码；
- 缺点：不是原生 DSH 工具；Dashboard 仍在 Hermes 9119；批量子代理仍由 Hermes 提供；
- 适合：只想“在 DSH 里触发 Hermes 迁移”。

### B. MCP Server 包装（1–2 天）

- 把 `flow_core` 包一个 MCP server（Python stdio），暴露 `flow_status/flow_plan/flow_quality/...`；
- DSH 的 MCP 面板添加该 server；
- 优点：工具模型可调用，跨宿主；
- 缺点：`flow_batch_auto` 的真实子代理仍需 Hermes/DSH 提供；UI 不集成。

### C. 原生 DSH 工具插件 + Python sidecar（推荐，3–5 天 PoC）

架构：

```text
DSH TypeScript plugin (cordis)
  ├─ defineTool: flow_status / flow_agents / flow_workflows
  ├─ defineTool: flow_plan / flow_batch_auto / flow_quality
  └─ spawns Python sidecar (JSON-RPC over stdio)
        └─ flow_core: registry / batch / quality / audit / experience / LoopX
              └─ launcher adapter:
                   ├─ DSH subagent API（最佳）
                   └─ 或 hermes chat --oneshot 子进程（过渡）
```

关键工作：

1. `dsh-hermes-flow` npm 包：
   - `package.json` + `dsh.bundle.patch` + `lib/index.js`
   - `defineTool` 包装 34 个 flow 工具（先做核心 8–10 个）
   - `output.schema/render` 替换 `{ok,data}` JSON 字符串
2. Python sidecar：
   - `python -m flow_core.rpc`，JSON 行协议；
   - 复用现有 `FlowRuntime`/`BatchQueue`/`QualityJobManager`；
   - 数据目录默认 `~/.dsh/plugin-data/hermes_flow` 或独立。
3. Launcher：
   - 把 `SubagentLifecycleLauncher` 替换为 DSH subagent 适配；
   - 若 DSH API 暂不稳定，先 `hermes chat --oneshot` 子进程执行批次。
4. UI：
   - 先用 DSH 工具卡片呈现 plan/batch/quality；
   - 后续用 `dsh.client` 做 7 Tab（工作量大）。

安装形态（DSH 当前 CLI）：

```powershell
dsh plugin --profile web add link:E:\path\to\dsh-hermes-flow
```

参考 DSH 插件契约：

- [DSH plugin development skill](https://github.com/NanmiCoder/dsh-agent-teams/blob/main/.dsh/skills/dsh-plugin-development/SKILL.md?plain=1)
- [DSH 工具插件：defineTool 契约](https://dsh-plugin.org/zh/tutorials/develop-tool-plugin)
- [DSH plugin 写法（阿里云）](https://developer.aliyun.com/article/1767675)
- [@deepseek-ai/dsh](https://www.npmjs.com/package/@deepseek-ai/dsh)

### D. 全量 TypeScript 重写（2–4 周，不推荐）

- 把 `flow_core` 全部翻译 TS；
- 优点：无 Python 依赖、单语言；
- 缺点：质量采集/Chrome/审计/批处理全重写，回归成本高。

---

## 4. 判断与建议

| 目标 | 选型 |
|---|---|
| 只想在 DSH 里触发迁移 | A（skill+CLI） |
| 要原生工具、但不要求 DSH 内 UI | B/C |
| 要 DSH 内完整 7 Tab + 原生子代理 | C + 重写 Dashboard |
| 长期单一技术栈 | D |

建议先做 **C 的 PoC**：

1. sidecar + 8 个核心工具（status/agents/workflows/plan/batch_status/quality/audit/auto）；
2. launcher 用 `hermes chat --oneshot` 过渡；
3. 验证一个小项目 2–5 文件；
4. 再决定是否接 DSH subagent 和 UI。

---

## 5. 数据与并发注意

- 同一数据目录不能同时跑 Hermes 和 DSH 两个 driver；
- 若共享 `plugin-data/hermes_flow`，SQLite WAL 可读但 driver 文件锁只防同进程模型，跨宿主需额外锁；
- 建议 DSH 使用独立数据目录：
  `~/.dsh/plugin-data/hermes_flow`；
- 迁移目标项目同样要 git 分支/备份。

---

## 6. PoC 实现状态（2026-10-19）

已落地 `plugin/dsh-hermes-flow`：

- DSH 原生 `defineTool` 插件 + Python sidecar；
- 已注册工具：
  - `hermes_flow_status`
  - `hermes_flow_agents` / `hermes_flow_skills` / `hermes_flow_workflows`
  - `hermes_flow_scan_project`
  - `hermes_flow_run_start`
  - `hermes_flow_batch_plan` / `hermes_flow_batch_status`
  - `hermes_flow_quality_collect` / `hermes_flow_quality_gate`
  - `hermes_flow_backend`
  - `hermes_flow_experience_search`
  - `hermes_flow_audit`
- DSH 宿主工具 schema 已加载（本会话可见 `hermes_flow_*`）。
- Sidecar RPC 实测：status / workflows / scan_project 正常。
- 数据目录：`~/.dsh/plugin-data/hermes_flow`。

### 当前安装方式（本机 desktop profile）

本机 `desktop` profile 的 pnpm store 与 DSH 自带 pnpm 不一致，标准 `dsh plugin add` 会报 `ERR_PNPM_UNEXPECTED_STORE`。PoC 用：

1. `npm pack` 生成 tarball；
2. 解包/复制到 `~/.dsh/profiles/desktop/node_modules/dsh-hermes-flow`；
3. 在 profile `cordis.patch.yml` 追加：
   ```yaml
   - insert:
       - id: hermes-flow
         name: dsh-hermes-flow
   ```
4. 重启 DeepSeek Harness。

其他机器若 pnpm store 正常，优先标准安装：

```powershell
dsh plugin --profile desktop add file:E:\deepSeek\plugin\dsh-hermes-flow\dsh-hermes-flow-0.1.0.tgz
```

### 尚未实现

- `hermes_flow_batch_auto`：需要把 `SubagentLifecycleLauncher` 换成 DSH subagent 适配，
  或过渡为 `hermes chat --oneshot` 子进程；当前批次真实转换仍由 Hermes 执行。
- DSH 内 Dashboard/7 Tab（需要 `dsh.client` UI 插件）。
- DSH 侧 `pre_llm_call` 记忆注入（需要 DSH hook）。
