# R5b Dashboard 收尾报告

- 日期：2026-10-18
- 目标：事件流/断线重放、人工门审批、节点级重跑、工作流 JSON 编辑
- 源码：[dashboard/src/index.js](../plugin/hermes_flow/dashboard/src/index.js) + [extra.css](../plugin/hermes_flow/dashboard/src/extra.css)
- 后端：[dashboard/plugin_api.py](../plugin/hermes_flow/dashboard/plugin_api.py)

## 1. 事件流（持久化 seq + cursor 重放）

- Run JSON 新增 `events[]`：`{seq, at, type, data}`，最多保留 500 条。
- `runtime.record_event()` 在以下时点写入：
  `created`、`batch_plan`、`batch_claimed`、`batch_ingest`、`batch_complete/fail/split/repair`、
  `driver`、`batch_event`、`status`、`gate_approve/gate_reject`、`node_rerun`。
- `GET /runs/{run_id}/events?after=<seq>` 返回增量事件与 `last_seq`。
- UI 以 cursor 每 2.5s 拉取；断线后从上次 `last_seq` 继续补齐，不清空已显示事件。

实测：`run-20261018-164908-3eaf` 事件流显示 `#1 created`、`#2 batch_plan`、`#3 gate_approve`、`#4 node_rerun`，console error 0。

## 2. 人工门审批

- `POST /runs/{run_id}/gate` body `{action:"approve"|"reject", reason}`。
- approve：若所有批次组完成 → Run `done`，否则 `running`；reject：`cancelled`；写入 `gate_history` 与事件。
- UI 仅在 `run.status === "gated"` 时显示「批准 / 驳回」。

## 3. 节点级重跑

- `POST /runs/{run_id}/nodes/{node_id}/rerun`：将该节点批次组内 `failed` 批次重置为 `ready`、attempt=0，并写事件。
- UI 在批次组 header 出现失败批次时显示「重跑失败」按钮。
- API 实测：`retried=0`（无失败批次时正确返回 0），Run 状态恢复 `running`。

## 4. 工作流 JSON 编辑

- 工作流详情新增可折叠 JSON 编辑器，保存走 `POST /workflows`（校验/持久化）。
- 支持修改节点/边/agent/batch 参数；保存后重新加载 DAG。

## 5. 验证

| 项 | 结果 |
|---|---|
| 事件 API | `after=0` 2 条、`after=1` 1 条，`last_seq=2` ✅ |
| gate API | approve → `running`，事件 `gate_approve` ✅ |
| rerun API | 200，`retried` 字段正常 ✅ |
| UI 事件时间线 | 4 条事件渲染，CDP console error 0 ✅ |
| 全量单测 | **69/69** 新单测、123/123 legacy ✅ |
| 安装/doctor | 34 tools / 1 hook ✅ |

截图：[运行/事件流](assets/r5b-runs.png)、[工作流编辑](assets/r5b-workflow-editor.png)。

## 6. 剩余

- 质量采集按钮仍是同步请求（build+browser 约 30s），可改异步任务/进度。
- 可视化 DAG 拖拽编辑未做；当前为 JSON 编辑 + 只读节点视图。
- 事件流是轮询增量，不是 WebSocket 推送（已满足断线重放）。
