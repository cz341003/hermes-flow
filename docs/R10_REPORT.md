# R10 工程化报告：CI / 打包 / 版本化 / 质量自动挂载

- 日期：2026-10-18
- 版本：**0.2.0**
- 产物：`plugin/hermes_flow/dist/hermes_flow-0.2.0.zip`（290,199 bytes）+ `.sha256`

## 1. 测试可移植（CI 前置）

- 所有测试/脚本不再硬编码 `E:\deepSeek\plugin\.tmp`：
  `FLOW_TEST_TMP`（CI 设置）→ 否则 `tempfile.gettempdir()`。
- 修正 `smoke_core.py` 的插件根路径为 `Path(__file__).parents[1]`。
- 本机用 PM Python 跑 `scripts/ci_local.ps1`：**compileall + 75 单测 + 123 legacy + smoke_core 全部通过**。

## 2. GitHub Actions

`.github/workflows/hermes-flow-ci.yml`：

| Job | 内容 |
|---|---|
| `unit` (ubuntu, py3.11/3.12) | compileall、Dashboard 静态冒烟、`tests` 75 单测、`tests/legacy` 123、smoke_core |
| `unit` (windows, py3.12) | 75 单测、123 legacy |

- 触发：`plugin/hermes_flow/**` 变更 / PR。
- 临时目录使用 `${{ runner.temp }}/flow-tmp`。
- 浏览器/真实项目相关用例在 CI 上按 fixture 缺失自动 skip。

## 3. 打包与版本化

- `scripts/package.py`：
  - 从 `plugin.yaml` 读版本；
  - 打包 `plugin.yaml/__init__/tools/runtime/flow_core/agents/skills/workflows/dashboard/tests/scripts/CHANGELOG`；
  - 排除 `__pycache__/*.pyc/.tmp/dist`；
  - 输出 `dist/hermes_flow-<version>.zip` + `.zip.sha256`。
- 版本升到 **0.2.0**：`plugin.yaml`、`dashboard/manifest.json`、`__init__.__version__`、runtime status、Dashboard settings。
- 本地 `scripts/ci_local.ps1` 提供 Windows 一键 CI。

## 4. 质量自动挂 driver（可选）

`flow_batch_auto(quality=true, browser=true)`：

- 批次全部完成后自动 `quality_collect`（build/typecheck/browser）；
- 调用聚合门（batch scores + coverage + build/browser）；
- 结果写入 `out["quality"]` / `run["quality"]`，并写 `quality` 事件；
- 聚合门非 pass → `quality_gate_failed=true`、Run 置 `gated`；
- 默认 `quality=false`，避免每次批驱动都额外 build/browser。

## 5. 验证

| 项 | 结果 |
|---|---|
| 本地 CI（compileall + tests + legacy + smoke） | ✅ |
| 新单测 | 75/75 |
| legacy | 123/123 |
| package zip | 290,199 bytes |
| sha256 | `8382c3299f7770c5cc19c0d45bf39babdf05e10b93f5496dc3f34082129e5094` |
| Dashboard 静态冒烟 | ✅ v0.2.0、bundle 21,516 bytes |
| doctor | 34 tools / 1 hook |

## 6. 限制

- GitHub Actions 未在本机实际触发（工作区不是 GitHub 仓库）；YAML 与命令已本地逐条验证。
- CI 不跑真实浏览器/真实 LLM（fixture/成本原因），只跑静态/单元/smoke。
- zip 未签名、未发布到市场；发布需 Git tag + Release。
- 质量自动挂载是可选参数，默认不开启，避免每个批次额外 30s 级 build/browser。
