---
name: 浏览器自动化验证
description: 启动真实浏览器逐路由验证 Vue3 页面渲染、交互、控制台与网络，采集可复现证据。
version: 1.0.0
id: vue3-verify
phases: [verify]
tags: [vue2, vue3, verify, browser, playwright, evidence]
---

# 浏览器自动化验证

静态检查通过不代表页面能用。本技能在真实浏览器里逐路由走一遍，把「白屏、路由 404、控制台红错、接口 4xx」变成可复现的截图与步骤。

## Procedure

1. 启动开发服务器：优先 `pnpm dev --host 127.0.0.1 --port 4173`（项目无 pnpm 则 `npm run dev -- --host 127.0.0.1 --port 4173`），用 `terminal` 轮询 `http://127.0.0.1:4173/` 直到返回 200；记录 PID 以便收尾。
2. 从 `src/router` 提取路由表，生成待测清单：`path`、`name`、`meta.auth`、是否懒加载。至少覆盖首页、列表页、详情页、表单页、404 页。
3. 用 `browser_navigate` 逐路由打开，等待 `networkidle` 或目标选择器出现（不要用固定 sleep 截空页）。
4. 每个路由采集：
   - 渲染：页面根节点存在、关键文本/表格行数/空态与基线一致。
   - 控制台：`error` 与 `warning` 全量记录（含堆栈首行）。
   - 网络：`4xx/5xx`、失败懒加载 chunk、重复请求。
   - 截图：首屏 + 关键交互后各一张，命名 `<route>-<state>.png`。
5. 每个页面至少做一个代表性交互：列表筛选/分页、表单输入与提交、弹窗打开关闭、路由跳转。交互后重新采集控制台，确认没有新增错误。
6. 与 Vue2 基线截图对比：布局偏移、字体、颜色、表格列、按钮位置；差异超过阈值时记录为 `visual_diff`。
7. 收尾：关闭浏览器上下文并结束 dev server 进程，避免端口占用影响下一批。
8. 输出 `reports/verify.json` 与失败复现步骤（路由、操作序列、预期/实际、截图路径）。

```json
{
  "dev_server": {"url": "http://127.0.0.1:4173", "started": true, "stopped": true},
  "routes": [
    {"path": "/users", "render": "ok", "console_errors": 0, "network_failures": 0,
     "screenshots": ["evidence/users-list.png"], "interactions": ["filter", "pagination"]},
    {"path": "/users/42", "render": "blank", "console_errors": 1,
     "console": ["TypeError: Cannot read properties of undefined (reading 'name')"],
     "screenshots": ["evidence/user-detail-blank.png"]}
  ],
  "visual_diff": [{"route": "/users", "ratio": 0.032, "baseline": "baseline/users.png"}],
  "failures": [{"route": "/users/42", "steps": ["打开 /users/42"], "expected": "详情渲染",
                "actual": "白屏 + 控制台 TypeError"}]
}
```

## Pitfalls

- 路由懒加载 chunk 404 表现为白屏而非报错页，必须看 network 与 `browser_console`，只看截图会误判为样式问题。
- 异步数据未返回就截图会得到空表格；等目标选择器或 `networkidle`，不要固定 sleep 2 秒。
- 需要登录的页面要用测试账号或 fixture 注入会话，否则 401 失败与迁移无关，会污染评分。
- `vite` 默认端口被占用时会自动换端口，脚本必须读取真实端口，不能写死 5173。
- HMR 可能在多次导航后保留旧状态；每轮验证前刷新页面或重启 dev server。
- dev server 未关闭会占住端口并让下一批启动失败，务必在 `finally` 里 kill。
- 浏览器控制台里的第三方警告（DevTools、extension）要过滤，只保留应用自身错误。

## Verification

- 路由清单的每一页都有 `render` 结果与至少一张非空截图。
- 控制台错误与网络失败被原样记录，没有「已忽略」但无说明的条目。
- 每个代表性交互执行完成，且没有产生新的控制台 error。
- `failures` 每条都包含可复现步骤、预期、实际与证据路径。
- dev server 已停止，端口可再次监听。
