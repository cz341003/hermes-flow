# v0.3.0 GitHub Release 记录

- 日期：2026-10-18
- 仓库：https://github.com/cz341003/hermes-flow
- Release：https://github.com/cz341003/hermes-flow/releases/tag/v0.3.0
- Tag：`v0.3.0`（annotated，指向 `39d2d9a` / release commit）
- 认证：SSH key `SHA256:Mj02EuyrpAKRgIQRW3n0BDCMsQZFzK+EdzutKEOxtQQ`（账号 `cz341003`）
- GitHub Release 通过 gh OAuth device flow（`repo` scope）创建

## 1. 已推送

- `main`：`39d2d9a release: v0.3.0 (R9 LoopX, DAG drag, async quality)`
- 历史 tag：`v0.2.0`
- 当前 tag：`v0.3.0`

## 2. Release 附件

| 附件 | 大小 | sha256 |
|---|---|---|
| `hermes_flow-0.3.0.zip` | 303,707 bytes | `a69e186eaf534f5de6274b8dabef4ee46e9257e3e90dba4688647f19e4457f76` |
| `hermes_flow-0.3.0.zip.sha256` | 89 bytes | — |
| `hermes_flow-0.3.0-source.zip` | 5,310,641 bytes | tag 源码快照 |

## 3. 发布内容

- R9 LoopX：`backend=sqlite|loopx`、JSONL `LoopXKernel`、CLI doctor/backend、降级。
- DAG 拖拽编辑：拖拽布局、添加/删除节点、`meta.x/y` 持久化。
- 异步质量：`QualityJobManager`、`/quality/jobs`、UI 后台轮询。
- 全量 84/84 新单测、123/123 legacy；`hermes plugins doctor` 34 tools / 1 hook。

## 4. 说明

- GitHub Release 需要 API 凭据，本次使用 GitHub OAuth device flow 临时 token；未写入磁盘/仓库。
- 安装包为 `hermes_flow-0.3.0.zip`，解压后可直接 `import hermes_flow`（已验证 version 0.3.0、dashboard/dist、cli.py）。
