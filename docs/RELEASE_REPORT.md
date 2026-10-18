# v0.2.0 Git Tag / Release 记录

- 日期：2026-10-18
- 仓库：`E:\deepSeek`（本地初始化，分支 `main`）
- Tag：**`v0.2.0`**（annotated）
- Tag commit：`5a4b77d`（后续文档提交会移动 tag）
- 发布附件：`releases/0.2.0/`

## 1. 仓库状态

```text
$ git log --oneline
5a4b77d docs: add v0.2.0 release notes
b1e0657 release: hermes_flow v0.2.0

$ git status --short
(clean)
```

- `.gitignore` 已排除：`apiKey.txt`、`.env`、`node_modules`、`plugin/r2-work`、测试产物、发布 zip、日志。
- 源码提交 281 个文件，约 6.5 MB（不含依赖/大 fixture）。
- tag 指向 commit `5a4b77d`，包含 `plugin/hermes_flow` 0.2.0、docs、CI、CHANGELOG。

## 2. Release 附件

| 文件 | 大小 |
|---|---|
| `releases/0.2.0/hermes_flow-0.2.0.zip` | 290,199 bytes |
| `releases/0.2.0/hermes_flow-0.2.0.zip.sha256` | 89 bytes |
| `releases/0.2.0/RELEASE_NOTES.md` | 2,874 bytes |
| `releases/0.2.0/hermes_flow-0.2.0-source.zip` | Git tag 源码快照 |

sha256：

```text
8382c3299f7770c5cc19c0d45bf39babdf05e10b93f5496dc3f34082129e5094  hermes_flow-0.2.0.zip
```

## 3. 为什么没有 GitHub Release

当前工作区：

- 不是 GitHub 仓库（无 `origin`）；
- 未安装 `gh` CLI；
- 没有远端地址/凭据。

因此本次完成的是 **本地 annotated tag + 本地 Release 附件 + 发布说明**；GitHub Release 需要远端后执行：

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

## 4. 发布校验

- [x] `plugin.yaml` / dashboard manifest / runtime status = 0.2.0
- [x] 75 新单测 + 123 legacy 通过
- [x] `hermes plugins doctor` 34 tools / 1 hook
- [x] zip 内容含 `plugin.yaml`、`__init__.py`、`flow_core`、`dashboard/dist`、agents/skills/workflows
- [x] zip 不含 `apiKey.txt` / `.env` / `node_modules` / `.tmp`
- [x] sha256 已写入 `.zip.sha256` 和 Release Notes
- [x] git 工作区 clean

## 5. 后续

1. 配置 GitHub 远端并推送 `main` + `v0.2.0`。
2. 安装 `gh` 后创建 GitHub Release（或网页上传 zip + sha）。
3. 1000 文件真实 LLM 迁移按预算执行；R9 LoopX 可选。
