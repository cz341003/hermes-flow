# R5 Dashboard 补齐报告（v2）

- 日期：2026-10-18
- 前端源码：[dashboard/src/index.js](../plugin/hermes_flow/dashboard/src/index.js) + [extra.css](../plugin/hermes_flow/dashboard/src/extra.css)
- 构建产物：[dashboard/dist/index.js](../plugin/hermes_flow/dashboard/dist/index.js)（19 KB IIFE，React 由宿主 SDK 提供）
- 旧版备份：`dashboard/dist/index.v1.js` / `style.v1.css`
- 后端：[dashboard/plugin_api.py](../plugin/hermes_flow/dashboard/plugin_api.py)

## 1. 新 UI（7 Tab）

| Tab | 数据源 | 功能 |
|---|---|---|
| 专家 | `/agents` + `/agent-status` | 专家卡、技能 chips、批次策略、**运行态**（活跃批次/进度） |
| 技能 | `/skills` + `/skills/{id}` | 技能列表、阶段/tag、点击查看 SKILL.md 正文 |
| 工作流 | `/workflows` + `/workflows/{id}` | 模板卡、只读 DAG、节点/边、创建 Run 表单 |
| 运行 / 批次 | `/runs` + `/runs/{id}` + `/groups` + `/batches/{id}/items` | Run 列表、节点步进、批次表、文件明细、暂停/继续/取消；driver/audit 侧栏 |
| 质量 | `/quality` + `/quality/collect` | 真实 build/typecheck/Chrome CDP 采集、路由结果、历史证据 |
| 记忆 | `/memory/experiences` GET/POST | 经验搜索、列表、新增经验 |
| 设置 | `/settings` + `/drivers` + `/audit` | 数据目录、阈值、driver 限制、注册错误、API 索引 |

- 保持宿主深色主题；所有文字使用字面色，避免 `--foreground=transparent` 再次导致不可见。
- 顶部 KPI、在线状态、当前 Run、5s 轮询；所有 Tab 真实数据，无 mock。
- 旧版 3 Tab 的专家/工作流/运行能力全部保留并增强。

## 2. 新增后端 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/agent-status` | 专家 → 活跃 Run/批次进度 |
| GET | `/skills/{id}` | 技能详情 + SKILL.md 正文 |
| GET | `/workflows/{id}` | 工作流完整 definition |
| GET/POST | `/memory/experiences` | 经验搜索 / 新增 |
| GET | `/quality` | 质量证据列表 |
| POST | `/quality/collect` | 真实 build + typecheck + browser 采集 |
| GET | `/audit` | 越界违规证据 |
| GET | `/drivers` | driver 锁/活跃状态 |
| GET | `/settings` | 数据目录、计数、阈值、driver 限制 |

## 3. 验证

- 无头 Chrome CDP 逐 Tab 点击并截图：**7/7 Tab 正常渲染，console errors = 0**。
- 新 API 在运行中的 Dashboard 全部返回 200（`/agent-status`、`/quality`、`/audit`、`/drivers`、`/settings`、`/memory/experiences`、`/skills/{id}`、`/workflows/{id}`）。
- 截图：
  - 专家：[r5-experts.png](assets/r5-experts.png)
  - 技能：[r5-skills.png](assets/r5-skills.png)
  - 工作流：[r5-workflows.png](assets/r5-workflows.png)
  - 运行 / 批次：[r5-runs.png](assets/r5-runs.png)
  - 质量：[r5-quality.png](assets/r5-quality.png)
  - 记忆：[r5-memory.png](assets/r5-memory.png)
  - 设置：[r5-settings.png](assets/r5-settings.png)

## 4. 构建方式

```powershell
node E:\DeepSeek\plugin\r2-work\node_modules\esbuild\bin\esbuild `
  E:\DeepSeek\plugin\hermes_flow\dashboard\src\index.js `
  --bundle --minify --format=iife --platform=browser --target=es2018 `
  --outfile=E:\DeepSeek\plugin\hermes_flow\dashboard\dist\index.js
# CSS = 旧 style.css（v1）+ dashboard/src/extra.css
```

## 5. 未完成 / 后续

- R5b 已补齐：事件流 cursor 重放、人工门批准/驳回、节点级重跑、工作流 JSON 编辑。
- 质量采集按钮仍同步等待 build+browser（约 30s），后续可改异步任务 + 进度。
- 可视化 DAG 拖拽编辑未做（当前 JSON 编辑 + 只读节点视图）。
- Dashboard 前端 CDP 截图脚本为手工验证，尚未入 CI。
