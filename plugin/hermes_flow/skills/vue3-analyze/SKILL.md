---
name: Vue3 结构分析
description: 盘点 Vue2 工程结构、技术栈与遗留 API，产出可执行的迁移范围、风险与批次建议。
version: 1.0.0
id: vue3-analyze
phases: [analyze]
tags: [vue2, vue3, analyze, structure, inventory]
---

# Vue3 结构分析

在动手改任何代码之前，把 Vue2 工程盘成一份可被依赖分析、批次规划和 Dashboard 直接消费的机器可读清单。本阶段严格只读，目标是「不多不少地知道要迁移什么」。

## Procedure

1. 读构建与版本事实：`package.json`、锁文件、`vue.config.js` / `vite.config.*`、`.browserslistrc`、`jsconfig.json` / `tsconfig.json`，记录 Vue 版本、构建工具、UI 库、状态管理、路由、Less/Sass、Node 版本与包管理器。
2. 用 `search_files` 枚举源码：`*.vue`、`*.js`、`*.jsx`、`*.ts`、`*.tsx`，排除 `node_modules`、`dist`、`build`、`coverage`、`.git`、`public/vendor`。
3. 读入口与全局装配：`src/main.*`、`App.vue`、`router/*`、`store/*`、`plugins/*`、`directives/*`、`filters/*`，确认 `new Vue`、`Vue.use`、`Vue.component`、`Vue.prototype`、`Vue.directive` 的注册面。
4. 逐文件分类：`page` / `component` / `layout` / `mixin` / `directive` / `filter` / `router-config` / `vuex-module` / `util` / `style` / `config` / `test`。每个文件必须恰好归入一类，`.js` 里的 render 函数按 `component` 处理。
5. 用 `search_files` 统计遗留 API 命中，至少覆盖：`filters:`、`mixins:`、`this.$listeners`、`this.$scopedSlots`、`$on(`/`$off(`/`$once(`、`Vue.prototype`、`Vue.extend`、`new Vue(`、`.sync`、`slot-scope`、`require.context`、`ztree`、`moment(`。每类记录命中文件与行号。
6. 评估复杂度：行数、脚本/模板/样式行数、`v-for` 嵌套深度、`v-if` 链、动态 `import()`、超大组件（>800 行）、跨目录引用。把「行数大 + 遗留 API 多 + 被引用多」的文件标为 high risk。
7. 输出 `reports/analyze.json`，并在回复中给出 5 行以内摘要（文件总数、组件数、Top 3 技术债、批次建议）。

```json
{
  "project_root": "E:/project/admin",
  "stack": {"vue": "2.6.14", "build": "webpack", "ui": "ant-design-vue@1.7.8",
            "state": "vuex@3.6", "router": "vue-router@3.5", "less": "4.x"},
  "counts": {"vue": 287, "js": 41, "ts": 0, "total": 328},
  "files": [{"path": "src/views/UserList.vue", "type": "page", "loc": 412,
             "legacy": ["filters", "this.$listeners"], "risk": "high"}],
  "legacy_hits": {"filters": 12, "mixins": 7, "this.$listeners": 5,
                  "require.context": 2, "ztree": 3},
  "risk_top": [{"path": "src/components/TreeSelect.vue",
                "reason": "812 行 + ztree + 自定义指令", "score": 9}],
  "batch_hint": {"waves": 4, "hot_files": ["src/components/TreeSelect.vue"]}
}
```

## Pitfalls

- 只扫 `.vue` 会漏掉 `render(h)` 组件、`Vue.component` 全局注册组件和 `require.context` 自动注册的组件；必须补扫 `.js`。
- `import()` 与 `require.context` 产生的组件不会出现在普通 import 图中，却会进入路由和页面，漏掉就会低估 287 的规模。
- 路径别名 `@/`、`~`、`@components` 不是文件系统路径；先把别名映射抄下来，否则后续依赖分析会解析失败。
- `.vue` 文件中的 `<script src="./x.js">` 与 `extends` / `mixins` 会跨文件继承逻辑，只读单个 SFC 会误判「无遗留 API」。
- 生成代码目录（`src/generated`、`public/vendor`、`dist`）必须排除，否则文件数虚高并拖慢后续批次。
- 遇到 `.env`、证书、密钥文件只记录路径，不读内容、不写入报告。

## Verification

- 文件清单去重后与 `search_files` 枚举总数一致，每个文件只出现一次且只归一类。
- 六类核心遗留 API（filters、mixins、`this.$listeners`、`this.$scopedSlots`、`.sync`、`Vue.prototype`）均有命中数或显式声明「未发现」。
- 所有 >800 行组件都进入 `risk_top`，且每条风险都带具体理由。
- 报告写入 `reports/analyze.json` 且可被 `json.load` 解析；工作区 `git status` 无源码改动。
