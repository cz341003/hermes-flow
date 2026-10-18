# HERMES Flow v0.2.0

> Vue2 → Vue3 迁移控制面 Hermes 插件。
> 发布日期：2026-10-18

## 亮点

- **34 个 `flow_*` 工具**、8 专家、12 技能、2 工作流模板、`pre_llm_call` 钩子。
- **真实迁移闭环**：20 文件 sample-app → Vue3 + Pinia + Router4 + Vite，8/8 批、20/20 applied、全部 pass。
- **真实质量门**：vite build（3180 modules）、typecheck、Chrome CDP 4/4 路由、聚合门 97.22。
- **写入边界审计**：基线 + 每批 diff，越界自动回滚并置 Run `gated`。
- **Dashboard v2（7 Tab）**：专家 / 技能 / 工作流 / 运行批次 / 质量 / 记忆 / 设置；事件流断线重放、人工门、节点重跑、工作流 JSON 编辑。
- **记忆闭环**：每 turn 自动召回经验；批次失败自动沉淀（越界/限流/截断/返工/失败）。
- **同 wave 并行**：`concurrency=1..3`，独立 worktree，apply/audit 按 seq 稳定提交。
- **压测**：1000 文件规划 150 批/50 wave；100 批 + 10 次故障 100/100、0 failed；真实 6 文件 3 批 79s 全 pass；kill/restart attempt=2 恢复。
- **工程化**：CI（Linux/Windows）、本地 `ci_local.ps1`、`package.py`、版本 0.2.0、测试可移植。

## 验证

| 项 | 结果 |
|---|---|
| 新单测 | 75/75 |
| 前序 legacy | 123/123 |
| 真实 20 文件迁移 | 8/8 批、20/20 applied |
| 真实 build/browser | build pass、4/4 路由、聚合门 97.22 |
| 100 批 + 10 故障 | 100/100 done、0 failed |
| 真实 6 文件并行 | 3/3 done、6/6 applied |
| kill/restart | attempt=2 恢复 2/2 批、8/8 文件 |
| `hermes plugins doctor` | 34 tools / 1 hook |

## 安装

```powershell
# 从本仓库安装
powershell -ExecutionPolicy Bypass -File plugin\hermes_flow\install.ps1 -HermesHome E:\hermes -Copy
# 或解压 Release zip 后复制到 <HERMES_HOME>\plugins\hermes_flow
```

要求：Hermes Agent `>=0.22`；Python `3.9+`；Windows 子代理需 Git Bash。

## Release 附件

- `hermes_flow-0.2.0.zip`（294,930 bytes）
- `hermes_flow-0.2.0.zip.sha256`
  - `a17a90b9b6a78b09aed97e0fe5322e63c26e413e6a8efcc01c4cb0fb16c2b49e`

## 已知限制

- 1000 文件真实 LLM 迁移未执行；按 6 文件采样粗估约 3.5–4h wall，token 成本需 provider 账单。
- GitHub Actions 已配置但本工作区无 GitHub 远端，未实际触发；本地 CI 等价通过。
- Release zip 未签名；发布需 Git tag + GitHub Release。
- Dashboard 的 DAG 拖拽编辑、异步质量任务尚未实现（当前 JSON 编辑 + 同步采集）。

## 发布命令（有远端/gh 时）

```powershell
git remote add origin <your-repo-url>
git push -u origin main
git push origin v0.2.0
gh release create v0.2.0 `
  plugin/hermes_flow/dist/hermes_flow-0.2.0.zip `
  plugin/hermes_flow/dist/hermes_flow-0.2.0.zip.sha256 `
  --title "HERMES Flow v0.2.0" `
  --notes-file docs/RELEASE_NOTES_v0.2.0.md
```
