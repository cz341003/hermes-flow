---
name: Vue3 依赖分析
description: 构建 Vue2 工程依赖图与版本矩阵，产出拓扑序、循环依赖分组和可执行的升级顺序。
version: 1.0.0
id: vue3-deps
phases: [deps]
tags: [vue2, vue3, deps, graph, topology, versions]
---

# Vue3 依赖分析

把「文件之间的引用关系」和「包版本之间的兼容关系」变成可执行的调度输入：批次必须按拓扑序走，版本必须按先运行时后生态的顺序升。

## Procedure

1. 读取 `reports/analyze.json` 与 `package.json`、锁文件，列出直接依赖与 devDependencies 的当前版本。
2. 逐个解析源码依赖边：静态 `import ... from`、`import 'x'`、`require('x')`、`import('./x')`、`require.context(...)`、`Vue.component` 全局注册、组件自动注册。每条边记录 `source -> target` 与引用类型。
3. 解析路径别名：从 `vue.config.js` 的 `configureWebpack.resolve.alias`、`jsconfig.json` 的 `paths`、`vite.config` 的 `resolve.alias` 中建立映射，把 `@/x`、`~x` 还原为真实路径；无扩展名导入补 `.js` / `.ts` / `.vue` / `/index.js`。
4. 构建有向图，跑拓扑排序。对强连通分量（环）做分组：同一环内的文件必须放进同一批、按固定顺序处理，禁止拆散到不同 wave。
5. 产出版本矩阵与升级顺序（用锁文件核对实际可安装版本）：
   - 运行时：`vue 2.x -> 3.4+`、`vue-router 3.x -> 4.x`、`vuex 3.x -> pinia 2.x`。
   - 构建：`webpack + vue-cli -> vite 5/6 + @vitejs/plugin-vue`。
   - UI：`ant-design-vue 1.x -> 4.x`、图标 `@ant-design/icons-vue`。
   - 样式：`less 3/4 -> 4.x`，检查 `javascriptEnabled` 与 `modifyVars` 的替代方案。
   - 工具：`moment -> dayjs`、`lodash` 按需引入、Node 引擎版本。
6. 计算 wave：入度为 0 的文件为 wave 0，去掉已处理节点后新的入度 0 为下一 wave；输出每个文件的 `wave` 与批内建议顺序。
7. 输出 `reports/deps.json`，包含 `graph`、`topo`、`waves`、`cycles`、`versions`、`upgrade_steps`、`risks`。

```json
{
  "topo": ["src/utils/request.js", "src/store/user.js", "src/views/UserList.vue"],
  "waves": [["src/utils/request.js"], ["src/store/user.js"], ["src/views/UserList.vue"]],
  "cycles": [["src/a.vue", "src/b.vue"]],
  "versions": {
    "vue": {"from": "2.6.14", "to": "3.5.x", "breaking": "global API / filters / v-model"},
    "vue-router": {"from": "3.5.4", "to": "4.4.x", "breaking": "createRouter / 通配符 / next"},
    "vuex": {"from": "3.6.2", "to": "pinia 2.2.x", "breaking": "mutations 移除"}
  },
  "upgrade_steps": ["先升 vue 与构建工具", "再升 router/pinia", "最后升 antdv 与 less"]
}
```

## Pitfalls

- 只解析 `import` 语句会漏掉 `Vue.prototype.$api`、全局组件、`require.context` 自动注册等隐式依赖；隐式边缺失会让批次在运行时报 `undefined`。
- 环状依赖不能报错了事：必须把环合并成一批，否则拓扑排序失败或运行顺序错误。
- `package.json` 的 semver 范围不等于锁文件实际版本；升级矩阵必须读锁文件，否则会给出装不上的版本。
- peerDependencies 冲突（`ant-design-vue@4` 要求 Vue 3、`vue-router@4` 要求 Vue 3）必须成组升级，单独升一个会在 install 阶段失败。
- 别名 `@/` 与 webpack 的 `resolve.extensions` 共同决定解析结果，少一个扩展名就会把 `.vue` 当外部包。
- 依赖图里不要把 `node_modules` 内部文件当源码节点，只保留项目源码路径。

## Verification

- 拓扑序中任一文件都排在其全部依赖之后；抽查 5 条边均满足 `index(source) < index(target)`。
- 所有环都被输出到 `cycles`，且环内文件落在同一 wave / 同一批。
- 依赖图文件集合等于结构分析的文件集合（允许显式标注的入口差异）。
- 版本矩阵每个包都有 `from`、`to`、`breaking` 三项，且 `to` 版本在锁文件或 registry 中可解析。
