# HERMES Flow 变更日志

## Unreleased

### 工作流编辑体验
- **集成 React Flow 12**：完整节点画布、端口拉线、Controls/MiniMap，React 19 宿主 shim。
- **MiniMap 优化**：200×150 → 118×78、右下 8px、半透明；新增「隐藏/显示总览」开关，避免遮挡画布。
- 修复模板卡选中态（`.hf2-card.hf2-selected`）。
- 修复「添加节点」无可见反馈：4 列/3 列网格可见位置 + 提示；新模板无 JSON 时回退 definition。
- 新增「节点与连线（表单编辑，无需 JSON）」：改 name/phase/agent/skill、增删节点、下拉增删/改连线；高级字段仍用 JSON。
- 调研文档：`docs/WORKFLOW_EDITOR_RESEARCH.md`（React Flow / Vue Flow / Rete / n8n / Windmill）。
- 构建：`dashboard/npm install && npm run build`；React 由宿主注入，bundle 约 219KB。

### WebUI 自定义入口
- 专家 Tab：新增专家表单（name/role/description/skills/model）。
- 技能 Tab：新增技能表单（name/description/phases/tags/正文），保存后直接打开 SKILL.md。
- 工作流 Tab：复制当前模板创建新工作流，再拖拽/增删节点/JSON 编辑/保存。
- 文档：`docs/USAGE_CUSTOMIZE.md`。

## 0.3.0（2026-10-18）

### R9 LoopX 后端
- `FlowRuntime(backend=sqlite|loopx)`；JSONL `LoopXKernel`（`.loopx/domain-state/`）。
- `hermes flow --backend loopx doctor`、`flow doctor`、`flow backend --set`。
- 未知 backend 自动降级 sqlite；真实 `loopx` CLI 通过 `LoopXBridge` 可选桥接。

### 体验
- DAG 拖拽编辑：绝对定位节点 + SVG 连线 + 添加/删除节点，位置保存到 `node.meta.x/y`。
- 异步质量任务：`QualityJobManager`、`/quality/collect` 默认返回 job、`/quality/jobs` 轮询；Dashboard 后台采集中状态。

### 测试
- 新增 LoopX（5）、DAG 编辑（2）、异步 job（2）单测；全量 84/84。

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
