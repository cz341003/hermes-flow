# HERMES Flow 变更日志

## 0.2.0（2026-10-18）

### 核心
- 批次自动 driver（真实 `ctx.subagent_lifecycle`）：claim → launch → ingest/apply → 质量门 → 重试/拆批/修复。
- 写入边界审计：基线 + 每批 apply 后 diff，越界自动回滚、`FLOW_BATCH_WRITE_SCOPE`、Run `gated`。
- 真实质量门：`vite build`、typecheck、Chrome CDP 路由验证、五信号聚合门。
- 真实 20 文件 Vue2→Vue3 迁移验收（8/8 批、20/20 applied、全部 pass）。

### Dashboard（7 Tab）
- 专家 / 技能 / 工作流 / 运行批次 / 质量 / 记忆 / 设置。
- 持久化事件流 + cursor 断线重放；人工门批准/驳回；节点级重跑；工作流 JSON 编辑。
- 修复：记忆页搜索按钮换行、宿主透明色导致文字不可见、`code` 白底。

### 记忆
- `pre_llm_call` 每 turn 注入相关经验（≤9k）+ Run 进度。
- 批次失败自动沉淀（`write_scope`/`rate_limit`/`truncation`/`quality_rework`/`migration_failure`）。

### 并行/压测
- 同 wave 并行 `concurrency=1..3`，每批独立 worktree，apply/audit 按 seq 串行。
- 真实 6 文件 3 批并行 79s 全 pass；kill/restart 真实进程恢复（attempt=2）。
- 1000 文件规划 150 批/50 wave；100 批 + 10 注入故障 100/100 done。

### 工程化
- 测试可移植（`FLOW_TEST_TMP`），非 Windows CI 可跑。
- GitHub Actions：Linux 3.11/3.12 + Windows 单测；本地 `scripts/ci_local.ps1`。
- `scripts/package.py` 生成 `dist/hermes_flow-<version>.zip` + sha256。
