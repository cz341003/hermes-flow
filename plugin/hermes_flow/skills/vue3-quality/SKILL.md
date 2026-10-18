---
name: 质量门控评分
description: 对迁移结果做五信号加权评分，输出可定位的缺陷清单与通过、警告或回环判定。
version: 1.0.0
id: vue3-quality
phases: [quality]
tags: [vue2, vue3, quality, gate, scoring, evidence]
---

# 质量门控评分

评分不是「打个分」，而是把五路证据折算成可复现的 0–100 分，并把每一个扣分点落到文件与行号上，供修复专家直接消费。

## Procedure

1. 收集五路信号，每路先单独给 0–100，再按权重合成：
   - AST 20%：用 `@vue/compiler-sfc` 解析模板与脚本，统计编译错误、已移除语法（`filters:`、`v-model` 旧写法、`slot-scope`）。
   - 构建 25%：对受影响 chunk 跑 `vite build`（或全量构建），0 error = 100，按 error 数衰减，warning 不扣构建分但要进缺陷清单。
   - 类型 15%：`vue-tsc --noEmit` 的 error 数，按文件统计；无 TS 项目则用 ESLint 的 `no-undef` / `vue/no-*` 代替并在报告注明。
   - 浏览器 25%：直接复用 `vue3-verify` 的 `console`、`network`、`render` 证据，有运行时错误按严重度扣分。
   - 行为 15%：对改动组件跑 Vitest / Playwright 用例，通过率折算；无用例时用 props/emits/slots 契约 diff 和基线截图比对代替。
2. 合成公式：`score = 0.20*ast + 0.25*build + 0.15*types + 0.25*browser + 0.15*behavior`，四舍五入到整数。
3. 判定：`>= 85 pass`，`70–84 warn`（可带缺陷放行），`< 70 rework`（回环修复，最多 3 轮）；任何一路为硬错误（SFC 编译失败、构建失败、页面白屏、核心用例失败）时，无论加权分多少都判 `rework`。
4. 生成缺陷清单：每条 `{file, line, signal, severity, message, fix_hint}`，`message` 必须是具体错误（如 `TS2339 Property 'modelValue' does not exist`），不能只写「类型错误」。
5. 写 `reports/quality.json` 并保留原始日志路径；批次场景下按文件归组，便于插件做批级门控。

```json
{
  "file": "src/components/TreeSelect.vue",
  "score": 64,
  "verdict": "rework",
  "signals": {"ast": 86, "build": 0, "types": 82, "browser": 91, "behavior": 81},
  "weights": [20, 25, 15, 25, 15],
  "defects": [
    {"file": "src/components/TreeSelect.vue", "line": 118, "signal": "build",
     "severity": "error", "message": "Failed to resolve import 'ant-design-vue/lib/tree'",
     "fix_hint": "改为 ant-design-vue/es/tree 或具名导入"}
  ],
  "evidence": {"build_log": "evidence/build-8430.log", "screenshot": "evidence/tree.png"}
}
```

## Pitfalls

- 语法通过 != 迁移通过：`filters:` 被删掉但模板仍引用同名变量时 SFC 能编译，运行时才报错，必须跑浏览器信号。
- 加权平均会掩盖单路 0 分：构建 0 分时即使其余 95 也要判 `rework`，硬错误优先于加权分。
- 只跑 `vite build` 不跑 `vue-tsc` 会漏掉 `.vue` 类型错误，尤其是 `modelValue`、`defineEmits` 的重载不匹配。
- 浏览器信号不能只截一张首页图；路由懒加载失败、登录后页面失败都要覆盖，否则 25% 权重虚高。
- 不要把格式 diff（prettier、引号、空格）算作缺陷，也不要把 warning 当 error 扣分，否则回环永远修不完。
- 缺陷必须带行号与证据路径；只写「重构后行为异常」无法驱动定点修复。

## Verification

- 五路信号都有数值且落在 0–100，合成分与公式计算结果一致（允许 ±0.5 舍入）。
- `verdict` 与阈值一致；`< 70` 时至少有一条 `severity=error` 的可执行缺陷。
- 每条缺陷都有 `file`、`signal`、`message`、`fix_hint`，证据路径真实存在。
- 硬错误（构建/编译/白屏）存在时判定必为 `rework`。
- 报告可被 `json.load`，批次内每个文件都有一条记录。
