---
name: 迁移缺陷修复
description: 依据质量与浏览器证据定位根因，做最小定点修复并回归验证，失败时升级而非硬撑。
version: 1.0.0
id: vue3-fix
phases: [fix]
tags: [vue2, vue3, fix, repair, rework, evidence]
---

# 迁移缺陷修复

修复的目标不是「让检查变绿」，而是消除证据里的根因，并且不制造新的契约破坏。每次只改与缺陷直接相关的行，改完立刻复跑对应信号。

## Procedure

1. 读 `reports/quality.json` 与 `reports/verify.json`，按 `severity` 排序，先修硬错误（构建失败、白屏、TS error），再修行为与视觉差异。
2. 对每条缺陷定位根因：读源文件上下文 + 相关 store/composable + 转换前后 diff，写出「为什么错」一句话，再动手。
3. 按信号选择修复模式：
   - 构建失败：补/改 import 路径、修 `require` 残留、修 Vite 不支持的语法、处理静态资源引用。
   - 类型错误：补 `defineProps` 类型、修 `modelValue`/`update:modelValue`、去掉隐式 `any` 并给出真实类型。
   - 浏览器错误：补 Pinia 初始化（`app.use(createPinia())`）、修 `useStore` 未在 setup 顶层调用、修事件名/插槽名、修懒加载路径。
   - 行为异常：对齐 `v-model`、事件 payload、`.sync` 迁移、路由参数读取方式。
   - 视觉差异：修 `:deep()`、scoped 样式穿透、antdv 组件结构变化、Less 变量注入。
4. 只改缺陷相关文件与直接依赖；如果必须改公共契约（props/emits/store），同步列出受影响的调用点并一起改。
5. 复跑对应检查：类型错误跑 `vue-tsc`，构建跑对应 chunk，运行时错误重跑该路由的浏览器验证，行为问题跑相关用例。
6. 输出修复摘要 `{file, defects_fixed, remaining, recheck, diff_lines}`；如果同一信号第 3 轮仍失败，停止修补并升级为人工门（`FLOW_LOW_SCORE` + `manual`），说明根因可能在转换策略而非局部代码。
7. 把可复用的根因写成 `experience_draft`（坑类型、触发条件、解法、适用版本），交给记忆归纳专家。

## Pitfalls

- 不要为了消掉报错把 Vue3 写法回退成 Vue2 风格（例如恢复 `filters` 语义、塞回 `this`），会被下一轮 AST 门重新打回。
- `as any` / `@ts-ignore` / `@ts-nocheck` 能让类型门变绿，但会把问题推给运行时；除非有注释说明和后续 issue，否则禁止。
- 改共享 props/emits/store 会波及未在批次内的调用点；只改一个文件会让其他页面在浏览器阶段挂掉。
- 同一个文件反复修同一个信号，通常说明第一次转换就错了；此时应回到 `vue3-transform` 重做该文件，而不是叠加补丁。
- 不要顺手重构、重命名、格式化；改动面越大，回滚和证据比对越困难。
- 修复后必须复跑检查；「看起来没问题」不能作为完成依据。
- 视觉差异不等于缺陷，先确认设计基线版本一致，再改样式。

## Verification

- 缺陷清单中每条都有处理结果：`fixed` 或 `remaining + reason`，不允许漏项。
- 复跑对应信号后分数提升或明确通过；原先的硬错误消失。
- 没有引入新的缺陷（重新跑完整五信号或至少相关信号）。
- 修复 diff 限定在批次/缺陷相关文件内，行数可解释。
- 同一信号连续 3 轮失败时已升级人工门，而不是继续重试。
