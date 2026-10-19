# dsh-hermes-flow (PoC)

DeepSeek Harness（DSH）原生工具插件：通过 `defineTool` 暴露 HERMES Flow 的核心能力，
底层用 Python sidecar 复用 `hermes_flow.flow_core`。

## 工具

- `hermes_flow_status`
- `hermes_flow_agents` / `hermes_flow_skills` / `hermes_flow_workflows`
- `hermes_flow_scan_project`
- `hermes_flow_run_start`（files 省略时自动扫描）
- `hermes_flow_batch_plan` / `hermes_flow_batch_status`
- **`hermes_flow_batch_auto`**：经 DSH `ctx.subagents` 启动子代理执行批次
- `hermes_flow_quality_collect` / `hermes_flow_quality_gate`
- `hermes_flow_backend`
- `hermes_flow_experience_search`
- `hermes_flow_audit`

## DSH launcher 实现

`hermes_flow_batch_auto` 的执行链：

```text
DSH tool execute(exec.agent)
  → Python sidecar BatchAutoDriver
      → claim batch
      → stdio __launch__ 请求
          → DSH ctx.subagents.start("spawn", { parent: exec.agent, prompt, signal })
          → 等待 run.result，取子代理最终文本
      → 子代理写 staging
      → ingest/apply/audit
      → complete/fail/split/repair
```

- 子代理结果必须是批次 JSON（`files:[{path,status}]`）；
- 当前 launcher **单并发**：同一 sidecar 只允许一个 `batch_auto`，`concurrency` 会被串行化；
- 子代理通过 DSH 的 spawn provider 运行；未注册 provider 时工具会明确报错。

## 安装

```powershell
# 先打包
cd E:\deepSeek\plugin\dsh-hermes-flow
npm pack

# 安装到当前 DSH profile（桌面版通常是 desktop；Web 版是 web）
dsh plugin --profile desktop add file:E:\deepSeek\plugin\dsh-hermes-flow\dsh-hermes-flow-0.2.0.tgz
```

如果本机 pnpm store 与 DSH 自带 pnpm 版本冲突（`ERR_PNPM_UNEXPECTED_STORE`），
按 `docs/DSH_PORT.md` 的 manual mount 步骤复制包 + 在 profile `cordis.patch.yml` 插入。

重启 DeepSeek Harness 后，新会话即可调用 `hermes_flow_*` 工具。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HERMES_FLOW_PLUGIN_ROOT` | `E:\deepSeek\plugin\hermes_flow` | 现有 Hermes 插件源码（含 flow_core） |
| `HERMES_FLOW_PYTHON` | `python` | Python 3.9+ 可执行文件 |
| `HERMES_FLOW_DATA_DIR` | `~/.dsh/plugin-data/hermes_flow` | DSH 侧独立数据目录 |

建议 DSH 使用独立数据目录，不要与 Hermes 同时驱动同一个批次组。

## 测试

```powershell
# 协议级测试：fake DSH launcher，真实 BatchAutoDriver + ingest/apply/audit
python tests/test_launcher_protocol.py
```

## 边界

- 已实现状态/注册表/扫描/规划/批次/真实质量采集/经验/审计，以及 `batch_auto` 的 DSH launcher；
- launcher 使用 DSH `ctx.subagents` + Python sidecar 双向 stdio 协议；
- **尚未跑真实项目验证**（按当前约定只做 launcher/接口验证）；
- 暂不支持 continuable/background 子代理、DSH Dashboard 7 Tab、`pre_llm_call` 记忆注入。
