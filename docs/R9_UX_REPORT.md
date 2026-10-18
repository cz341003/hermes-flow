# R9 LoopX 后端 + DAG 拖拽编辑 + 异步质量任务

- 日期：2026-10-18
- 状态：R9 完成；DAG 拖拽编辑完成；异步质量任务完成

## 1. R9 LoopX 后端

### 实现

- `FlowRuntime(..., backend="sqlite"|"loopx")`；后端解析优先级：
  `构造参数` → `HERMES_FLOW_BACKEND` → `<data_dir>/backend.json` → `sqlite`。
- `kernel` 通过 `create_kernel` 创建：
  - `sqlite` → 自研 `Kernel`（state.db）
  - `loopx` → `LoopXKernel`（JSONL domain-state ledger，`.loopx/domain-state/`）
- 未知 backend → **自动降级 sqlite**，并记录 `backend_error`（不阻塞启动）。
- CLI：
  - `hermes flow --backend loopx doctor`
  - `hermes flow doctor`
  - `hermes flow backend`
  - `hermes flow backend --set loopx|sqlite`（持久化到 `backend.json`）
- `status()` / Dashboard `/settings` 暴露 `backend`、`kernel_class`、`loopx_cli`、`kernel_ok`。
- `LoopXBridge` 保留真实 `loopx` CLI 桥接；未安装时给出清晰错误，JSONL 后端仍可用（不依赖 loopx wheel）。

### 实测

```text
$ hermes flow doctor
{"backend":"sqlite","kernel_ok":true,"kernel_class":"Kernel","loopx_cli":null}

$ hermes flow --backend loopx doctor
{"backend":"loopx","kernel_ok":true,"kernel_class":"LoopXKernel","loopx_cli":null}

$ hermes flow backend --set loopx   # backend.json 持久化
$ hermes flow status                 # backend=loopx
$ hermes flow backend --set sqlite   # 恢复
```

## 2. DAG 拖拽编辑

- 工作流页：绝对定位节点 + SVG 连线 + HTML5 drag/drop。
- 节点位置保存在 `node.meta.x/y`，随工作流 JSON 保存/回读。
- 支持：
  - 拖拽布局（自动写回 JSON）；
  - 「添加节点」（生成 `node-N`，默认 transform）；
  - 「删除选中」（同时删除关联边）；
  - JSON 编辑 + 保存（原有能力保留）；DAG 校验仍拒绝环。
- 位置无 meta 时按 4 列网格自动布局。

CDP 实测：

```json
{ "canvas": true, "nodes": 7, "afterAdd": 8, "left": "350px", "top": "195px", "textarea": true, "errors": [] }
```

截图：[docs/assets/r9-dag-editor.png](assets/r9-dag-editor.png)

## 3. 异步质量任务

- 新增 `flow_core/quality/jobs.py`：`QualityJobManager`，后台线程执行，内存保留 1 小时/最多 50 个。
- API：
  - `POST /quality/collect` 默认 `background=true` → 返回 `{job_id,status:"running"}`；
  - `POST /quality/collect` body `background=false` → 同步（兼容旧行为）；
  - `GET /quality/jobs`、`GET /quality/jobs/{id}`。
- Dashboard 质量页：提交后显示「后台采集中…」，1.5s 轮询 job；完成后自动展示结果。
- 实测 job：`qj-eb3b40b19bdf`，29.22s，build ✅、browser ✅（4/4 路由）。
- 任务状态：`running/done/error`，结果/错误/时间戳都可在 job 中查询。

## 4. 验证

| 项 | 结果 |
|---|---|
| LoopX backend 单测 | 5/5 |
| DAG 编辑单测 | 2/2 |
| 异步 job 单测 | 2/2 |
| 全量新单测 | **84/84** |
| 前序 legacy | **123/123** |
| `hermes flow --backend loopx doctor` | 34 tools 插件正常；LoopXKernel ok |
| DAG CDP | 7→8 节点、拖拽生效、console 0 |
| 质量 job | 29.22s、build/browser 均 pass |

## 5. 限制

- 真实 `loopx` CLI 未安装；当前使用等价 JSONL 后端（`LoopXBridge` 已保留桥接/清晰错误）。
- DAG 边目前通过 JSON 编辑添加/删除；拖拽只改布局/节点位置，不做端口连线。
- 质量 job 存在内存中，Dashboard 重启会丢失历史 job（质量证据文件仍在 `plugin-data/quality`）。
- 前端轮询不是 WebSocket 推送。
