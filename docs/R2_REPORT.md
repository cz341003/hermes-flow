# R2 真实迁移 E2E 报告（sample-app 20 文件）

- 日期：2026-10-18
- 运行：`run-20261018-154459-9a31`，批次组 `g-f02b7994bc`
- 项目：`E:\deepSeek\plugin\sample-app` → 复制到 `E:\deepSeek\plugin\r2-work`
- 驱动：`flow_batch_auto`（真实 `ctx.subagent_lifecycle` 子代理，非 mock）
- 原始数据：[r2-report.json](../plugin/tests/out/r2-report.json)

## 1. 结果摘要

| 指标 | 结果 |
|---|---|
| 文件数 | 20 |
| 批次 | **8 批 / 5 wave** |
| 完成批次 | **8/8，failed=0** |
| 文件状态 | **20/20 `applied`** |
| 批次评分 | 97.0 / 97.0 / 97.0 / 97.6 / 97.6 / 97.0 / 97.0 / 97.6，**全部 pass** |
| 重试批次 | b0004、b0006 各重试 1 次后通过 |
| 实际改写文件 | **19 个**；`src/utils/format.js` 内容未变 |
| 运行状态 | batch 层 `done=true`；Run 仍为 `running`（后续 quality/verify 节点未执行，属预期） |

## 2. 批次明细

| 批次 | 文件 | 状态 | score | attempt |
|---|---|---|---|---|
| b0001 | babel.config.js, index.html, package.json, loadingMixin.js, variables.less, format.js, request.js | done | 97.0 | 1 |
| b0002 | webpack.config.js | done | 97.0 | 1 |
| b0003 | global.less, HelloWorld.vue, TreeMenu.vue, UserCard.vue, store/modules/user.js | done | 97.0 | 1 |
| b0004 | Home.vue, App.vue, About.vue | done | 97.6 | 2 |
| b0005 | store/index.js | done | 97.6 | 1 |
| b0006 | UserList.vue | done | 97.0 | 2（首次 child timeout） |
| b0007 | router/index.js | done | 97.0 | 1 |
| b0008 | main.js | done | 97.6 | 1 |

## 3. 迁移结果抽查

- `package.json`：`vue ^3.4.21`、`pinia ^2.1.7`、`vue-router ^4.3.0`、`ant-design-vue ^4.1.2`、`vite ^5.2.8`；scripts 改为 `vite / vite build / vite preview`。
- `src/main.js`：`createApp(App)` + `app.use(pinia/router/Antd)`，移除 `Vue.use` 与 `productionTip`。
- `src/router/index.js`：`createRouter + createWebHistory`，含 `/:pathMatch(.*)*` fallback。
- `src/store/index.js`：`createPinia()` 默认导出 + `useUserStore` 重导出。
- 7 个 `.vue` 全部为 `<script setup>`，无遗留 `export default` Options API。

## 4. 本次暴露并修复的问题

1. **`max_seconds` 大于 Hermes 工具 420s 上限**
   - 首轮传 `max_seconds=900`，工具调用在 420s 被硬超时，driver 线程仍在跑并遗留锁，后续调用 `busy`。
   - 修复：driver 默认 `max_seconds=240`、硬上限 360s；工具 schema 同步；文档标注必须 <420s。
2. **driver 锁 TTL 过长 + 无心跳**
   - 原 `TTL = max(120, max_seconds*2+60)`，900s 调用留下约 31 分钟 stale lock，期间无法接管。
   - 修复：TTL 限制为 `max(120, min(420, max_seconds+60))`；每批 claim/完成后 `lock.touch()` 心跳；driver 正常退出 `finally` 释放。
3. **超长单批**
   - b0006（UserList.vue）首次 child timeout（66.5s）后自动回到 ready，第二次通过；属于预算内重试，不是数据损坏。

## 5. 复现方式

```powershell
# 1) 创建 r2-work + Run + 批次组
python E:\deepSeek\plugin\r2_setup.py
# 输出 run_id / group_id

# 2) 在 Hermes agent turn 内驱动（可重复调用直到 done）
flow_batch_auto(group_id="<group_id>", max_batches=5, max_seconds=240, apply=true)
flow_batch_status(group_id="<group_id>")
```

本次通过 `hermes chat --oneshot --query-file r2_prompt.txt -t hermes_flow,file,terminal --yolo` 执行；真实子代理写入 staging，driver 统一 apply 到 `r2-work`。

## 6. 结论与边界

- 结论：**真实 20 文件、8 批次、真实子代理转换 + staging apply 全部完成**，R2 达标。
- 边界：当前 score 仅来自 AST/diff/白名单 + 子代理自报，**没有真实 vite build / vue-tsc / Playwright**；下一任务 R3 接入真实质量采集。
- 边界：Run 只推进了 `transform` 批次节点；quality/verify/fix/review 节点尚未由 driver 自动推进（R5/后续工作流 driver）。
