# dsh-hermes-flow (PoC)

DeepSeek Harness（DSH）原生工具插件：通过 `defineTool` 暴露 HERMES Flow 的核心能力，
底层用 Python sidecar 复用 `hermes_flow.flow_core`。

## 工具

- `hermes_flow_status`
- `hermes_flow_agents` / `hermes_flow_skills` / `hermes_flow_workflows`
- `hermes_flow_scan_project`
- `hermes_flow_run_start`（files 省略时自动扫描）
- `hermes_flow_batch_plan` / `hermes_flow_batch_status`
- `hermes_flow_quality_collect` / `hermes_flow_quality_gate`
- `hermes_flow_backend`
- `hermes_flow_experience_search`
- `hermes_flow_audit`

## 安装

```powershell
# 先打包
cd E:\deepSeek\plugin\dsh-hermes-flow
npm pack

# 安装到当前 DSH profile（桌面版通常是 desktop；Web 版是 web）
dsh plugin --profile desktop add file:E:\deepSeek\plugin\dsh-hermes-flow\dsh-hermes-flow-0.1.0.tgz
```

重启 DeepSeek Harness 后，新会话即可调用 `hermes_flow_*` 工具。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HERMES_FLOW_PLUGIN_ROOT` | `E:\deepSeek\plugin\hermes_flow` | 现有 Hermes 插件源码（含 flow_core） |
| `HERMES_FLOW_PYTHON` | `python` | Python 3.9+ 可执行文件 |
| `HERMES_FLOW_DATA_DIR` | `~/.dsh/plugin-data/hermes_flow` | DSH 侧独立数据目录 |

建议 DSH 使用独立数据目录，不要与 Hermes 同时驱动同一个批次组。

## PoC 边界

- 已实现状态/注册表/扫描/规划/批次查询/质量采集/经验/审计；
- **未实现** `flow_batch_auto` 的真实子代理执行：需要把现有 `SubagentLifecycleLauncher`
  换成 DSH subagent 适配（或过渡为 `hermes chat --oneshot` 子进程）；
- 当前 `run_start`/`batch_plan` 可在 DSH 内记录与规划，但真正的批次转换暂由 Hermes 执行。
