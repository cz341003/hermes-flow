# HERMES Flow v0.3.0

> R9 LoopX 后端 + DAG 拖拽编辑 + 异步质量任务。
> 发布日期：2026-10-18

## 新增

- **R9 LoopX 后端**
  - `FlowRuntime(backend="sqlite"|"loopx")`；JSONL `LoopXKernel`（`.loopx/domain-state/`）。
  - `hermes flow --backend loopx doctor`、`hermes flow doctor`、`hermes flow backend --set`。
  - 未知 backend 自动降级 sqlite；真实 `loopx` CLI 通过 `LoopXBridge` 可选桥接。
- **DAG 拖拽编辑**
  - 绝对定位节点 + SVG 连线；拖拽布局、添加/删除节点；位置保存到 `node.meta.x/y`。
  - 保留 JSON 编辑；DAG 校验仍拒绝环。
- **异步质量任务**
  - `QualityJobManager`；`POST /quality/collect` 默认返回 job_id。
  - `GET /quality/jobs`、`GET /quality/jobs/{id}`；Dashboard 后台采集中状态。

## 验证

| 项 | 结果 |
|---|---|
| 新单测 | 84/84 |
| 前序 legacy | 123/123 |
| LoopX CLI | `sqlite` / `loopx` doctor 均通过（LoopXKernel ok） |
| DAG CDP | 7→8 节点、拖拽生效、console 0 |
| 质量 job | 29.22s、build/browser 4/4 pass |
| `hermes plugins doctor` | 34 tools / 1 hook |

## 安装

```powershell
powershell -ExecutionPolicy Bypass -File plugin\hermes_flow\install.ps1 -HermesHome E:\hermes -Copy
```

## Release 附件

- `hermes_flow-0.3.0.zip`（303,707 bytes）
- sha256：`a69e186eaf534f5de6274b8dabef4ee46e9257e3e90dba4688647f19e4457f76`

## 已知限制

- 真实 `loopx` CLI 未安装；当前使用等价 JSONL 后端。
- DAG 边仍用 JSON 编辑；拖拽只改节点位置。
- 质量 job 是内存态，Dashboard 重启后历史 job 丢失（质量证据文件保留）。
- 1000 文件真实 LLM 迁移未执行（预算项）。
