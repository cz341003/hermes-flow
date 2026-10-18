# R3 真实质量采集报告（build / typecheck / browser）

- 日期：2026-10-18
- 对象：R2 迁移产物 `E:\deepSeek\plugin\r2-work`（sample-app 20 文件）
- 采集器：[collectors.py](../plugin/hermes_flow/flow_core/quality/collectors.py) + [browser.py](../plugin/hermes_flow/flow_core/quality/browser.py) + [browser_probe.mjs](../plugin/hermes_flow/flow_core/quality/browser_probe.mjs)
- 工具：`flow_quality_collect`、`flow_quality_gate`；CLI `hermes flow verify`
- 证据：`plugin/tests/out/quality-*.json`、`plugin/tests/out/browser-*.json`、`plugin/tests/out/browser-*.png`

## 1. 实现

| 能力 | 说明 |
|---|---|
| build | 优先 `npm run build`；无 script 且有 vite 依赖时 `npx vite build` |
| typecheck | `type-check` / `typecheck` script；有 tsconfig 时 `npx vue-tsc --noEmit` |
| tests | 可选 `npm test` |
| browser | 启动 Vite preview，系统 Chrome + **零依赖 CDP 探针**（Node 内置 WebSocket）逐路由检查渲染、console/page/network 错误并截图；不会下载 Playwright 浏览器 |
| 证据 | exit_code / duration / log_tail / 路由结果 / 截图；JSON 写入 `plugin-data/quality/` |
| 聚合 | `flow_quality_gate` = 真实 build + batch_scores + coverage + browser → `aggregate_gate` |

额外修复：
- Windows esbuild 清理 `%TEMP%` 被 ACL 拒绝导致假失败 → `TMP/TEMP/TMPDIR` 指到项目内 `.quality-tmp`。
- 浏览器无条件请求 `/favicon.ico` 的 404 被识别为噪声（仅当所有 404 都是 favicon 时过滤），不掩盖真实资源错误。

## 2. Build：采集器抓到了 R2 的真实缺陷

第一次 build：

```text
[vite:build-import-analysis] src/App.vue (6:23)
Failed to parse source ... Install @vitejs/plugin-vue to handle .vue files.
```

R2 子代理迁移了 `package.json`（Vite 5）与 Vue 文件，但**没有生成 `vite.config.js`**，Vite 未启用 Vue 插件。这证明 R2 的 97 分（AST/diff/自报）不能代替真实构建质量。

补 `vite.config.js` 后：

```text
✓ 3180 modules transformed.
dist/assets/index-BIN2TTFy.js  1,532.21 kB
✓ built in 8.92s
```

`flow_quality_collect`：`build.ok=true`、exit 0、duration 约 9–11s。

## 3. Browser：4/4 路由通过

探针启动 `npm run preview`（Vite 5.4.21），用 Chrome headless + CDP 验证：

| 路由 | 结果 | DOM 节点 | console | page | network | 截图 |
|---|---|---|---|---|---|---|
| `/` | ✅ | 34 | 0 | 0 | 0 | `browser-_.png` |
| `/home` | ✅ | 34 | 0 | 0 | 0 | `browser-_home.png` |
| `/users` | ✅ | 72 | 0 | 0 | 0 | `browser-_users.png` |
| `/about` | ✅ | 37 | 0 | 0 | 0 | `browser-_about.png` |

截图示例：[home](../plugin/tests/out/browser-_home.png)、[users](../plugin/tests/out/browser-_users.png)。

## 4. 聚合门结果

`flow_quality_gate(project_root=r2-work, batch_scores=[97.0,97.0,97.0,97.6,97.6,97.0,97.0,97.6], coverage=1.0, browser=true)`：

```json
{
  "score": 97.22,
  "verdict": "pass",
  "coverage": 1.0,
  "reasons": []
}
```

- build ✅、browser ✅、coverage 1.0 ✅、平均分 97.22 ✅ → **pass**。
- 之前 browser=false 时同一组数据是 `rework`，原因仅“关键路由浏览器验证失败”；现在补齐。

## 5. 状态与边界

| 项 | 状态 |
|---|---|
| 真实 build 采集 | ✅ 已实测通过 |
| typecheck 采集 | ✅ 已实现；本项目无 tsconfig，按 `skipped` 记录 |
| tests 采集 | ✅ 可选实现；本项目无 test script |
| browser 路由验证 | ✅ Chrome + CDP，4/4 路由通过 |
| 自动接入 driver/聚合门 | 🟡 当前由 `flow_quality_collect/gate` 或 CLI 显式调用；尚未在 `flow_batch_auto` 末尾自动执行 |
| 多项目/Node 版本 | 🟡 只测了 Node 24 / Vite 5 |
| 视觉回归 | 🟡 目前做渲染/错误/截图，不做像素 diff |

## 6. 结论

R3 已完成：**真实 build + 真实浏览器路由验证 + 聚合门**，并在 R2 产物上实测 `pass(97.22)`。同时暴露并修复了 R2 的 `vite.config.js` 缺失问题。

下一步：
1. **R4 写入边界审计**（自动写工作区的安全底线）；
2. 把质量采集自动挂到 driver 的批次/聚合时点；
3. R5 Dashboard 补齐与 R8 压测。
