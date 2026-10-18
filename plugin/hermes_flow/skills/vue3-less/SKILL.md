---
name: Less 变量与主题迁移
description: 迁移 Less 全局变量、主题定制、样式穿透与 Vite 注入配置，保证 Vue3 页面视觉不回退。
version: 1.0.0
id: vue3-less
phases: [transform]
tags: [vue2, vue3, less, theme, css, style]
---

# Less 变量与主题迁移

Vue2 项目的视觉资产大多沉在 Less 变量与 `modifyVars` 里。构建工具换成 Vite、UI 库升到 antdv 4 后，变量注入方式和主题机制都变了；迁移目标是「颜色、间距、圆角、字体全部一致」。

## Procedure

1. 盘点 Less 资产：`src/styles/*.less`、`variables.less`、`mixins.less`、`theme.less`，以及 `vue.config.js` 中的 `css.loaderOptions.less`（`modifyVars`、`javascriptEnabled`、`globalVars`）。
2. 建立变量清单：主色、成功/警告/错误、文本色、边框、背景、圆角、字号、间距、阴影、层级。记录每个变量名与旧值，作为视觉验收基线。
3. Vite 注入全局变量：在 `vite.config.ts` 的 `css.preprocessorOptions.less.additionalData` 中 `@import "@/styles/variables.less";`，避免每个 `.vue` 手工 import。多个文件用 `@import (reference)` 防止重复输出。
4. 清理 webpack 语法：
   - `~` 前缀（`@import "~ant-design-vue/lib/style/index.less"`）在 Vite 中删除 `~`，改为包名路径或 `@` 别名。
   - `url('~@/assets/x.png')` -> `url('@/assets/x.png')`，并在 `resolve.alias` 配置 `@`。
   - `require()`、`module.exports`、`webpack` 相关 Less 插件删除。
5. Less 4 语法修正：默认 `math: 'parens-division'`，`10px / 2` 不再自动求值；需要旧行为时用 `~"10px / 2"` 或显式括号。`javascriptEnabled` 默认关闭，内联 JS 表达式改成预计算变量。
6. 样式穿透：`/deep/ .x`、`::v-deep .x`、`>>> .x` -> `:deep(.x)`；`::v-slotted` / `::v-global` 按需使用。全局样式放 `src/styles/index.less` 并在 `main.js` 引入。
7. antdv 主题：1.x 的 `modifyVars: { 'primary-color': '#35CFC1' }` 在 4.x 改为 `ConfigProvider` 的 `theme.token.colorPrimary`；Less 变量名从 `@primary-color` 变为 CSS-in-JS token，不要两套混用。
8. 主题切换（暗色/亮色）：用 CSS 变量承载，Less 只做静态计算；运行时 `document.documentElement.style.setProperty('--color-primary', ...)`，避免重新编译 Less。
9. CSS Modules：`.module.less` 保持；`composes` 与 `:global` 语法在 Vite 下兼容，但 `localsConvention` 需按旧配置设置。
10. 输出迁移说明：变量改名表、删除的 `~` 引用、主题注入方式、视觉基线截图对比。

```less
// variables.less（保留旧变量作为单一事实源）
@primary-color: #35cfc1;
@text-primary: #e6edf3;
@border-color: #1e262f;
@radius-base: 5px;
@space-sm: 8px;

// 组件内
.panel {
  border: 1px solid @border-color;
  border-radius: @radius-base;
  padding: @space-sm;
  :deep(.ant-table-cell) { padding: 10px 12px; }
}
```

```ts
// vite.config.ts
css: {
  preprocessorOptions: {
    less: {
      additionalData: '@import "@/styles/variables.less";',
      math: 'parens-division'
    }
  }
}
```

## Pitfalls

- `additionalData` 注入的变量文件里如果有实际 CSS 规则，会被重复打进每个组件；变量/混入文件必须只含声明，或用 `(reference)`。
- Less 4 除法行为改变，`@width / 2` 会原样输出为 CSS `calc` 式字符串，导致尺寸错乱；显式加括号或改 `math` 选项。
- `~` 前缀在 Vite 中不是别名而是普通字符，路径解析失败；全局搜索 `~` 逐个清理。
- `modifyVars` 对 antdv 4 不生效，因为样式是 CSS-in-JS 生成的；继续用会「看起来没坏但颜色没变」。
- `/deep/` 在 Vue3 SFC 编译器中已移除，保留会导致编译报错；统一 `:deep()`。
- 变量文件被 `@import (css)` 引入时不会参与 Less 计算，颜色仍是编译期字面量，主题切换失效。
- CSS 变量与 Less 变量同名混用会产生两套主题源；确定一个运行时变量前缀（如 `--app-*`）。
- 删除全局样式前确认 `main.js` 是否还引用 `ant-design-vue/dist/antd.css`；antdv 4 应改用 `reset.css`。

## Verification

- 全仓不再出现 `~@/`、`~ant-design-vue`、`/deep/`、`::v-deep`、`javascriptEnabled`、`modifyVars`。
- 关键页面截图与 Vue2 基线对比，主色、边框、圆角、间距无可见差异。
- `vite build` 产物中 Less 变量已编译为具体值，没有残留 `@primary-color`。
- 暗色/亮色切换只改 CSS 变量，无需重新构建；刷新后主题保持。
- 组件 scoped 样式能穿透到 antdv 内部节点（`:deep`），且不污染其他页面。
