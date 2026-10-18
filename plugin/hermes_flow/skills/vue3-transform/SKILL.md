---
name: Vue3 语法升级
description: 逐文件把 Options API、filters、mixins、this.$xxx 等 Vue2 写法转换为 Vue3 Composition API。
version: 1.0.0
id: vue3-transform
phases: [transform]
tags: [vue2, vue3, transform, composition-api, script-setup]
---

# Vue3 语法升级

一次只处理批次内的一个文件，先读后改，保持 props / emits / slots / 路由参数 / store 契约不变。转换后的文件写入 staging 目录，由插件校验后原子应用，绝不直接覆盖工作区。

## Procedure

1. 完整读目标文件与它直接依赖的 `composable` / `store` / `api` 文件；记录对外契约（props 名称与类型、emits 事件名、slots、`model` 选项、路由参数）。
2. 按映射表改写（Options API -> `<script setup>`）：
   - `data()` -> `ref()` / `reactive()`；对象统一 `reactive`，基本类型统一 `ref`。
   - `computed` -> `computed(() => ...)`；有 setter 的用 `computed({ get, set })`。
   - `watch` -> `watch(source, cb, { immediate, deep })`；`$watch` 字符串路径改成 getter 函数。
   - `methods` -> 普通函数；模板中仍可直接调用。
   - `created` / `mounted` / `beforeDestroy` -> `onMounted` / `onBeforeUnmount`，`beforeCreate`+`created` 逻辑上移到 setup 顶层。
   - `props` / `emits` -> `defineProps` / `defineEmits`，事件名保持 kebab-case 与父组件一致。
   - `provide` / `inject` -> `provide()` / `inject()`。
   - `this.$refs.x` -> 模板 `ref="x"` + `const x = ref(null)`。
   - `this.$route` / `this.$router` -> `useRoute()` / `useRouter()`。
   - `this.$store` -> `useUserStore()` 等 Pinia store。
   - `this.$nextTick` -> `nextTick()`。
3. 删除 Vue3 已移除的语法：`filters`（改成 `computed` 或普通函数并更新模板）、`$on`/`$off`/`$once`（改用 Pinia 或 `mitt`）、`this.$listeners`（并入 `$attrs`）、`this.$scopedSlots`（改 `$slots`）、`.sync`（改 `v-model:prop`）、`slot-scope`（改 `v-slot`）、`$set`/`$delete`（直接赋值或新建对象）。
4. 自定义组件 `v-model`：子组件 `props.modelValue` + `emits('update:modelValue')`；父组件 `v-model:title` 对应 `title` / `update:title`。
5. 全局 API：`Vue.component` -> `app.component`，`Vue.directive` -> `app.directive`，`Vue.prototype.$x` -> `app.config.globalProperties.$x` 或 `provide/inject`。
6. 样式与模板：`::v-deep` / `/deep/` -> `:deep()`，`v-if` 与 `v-for` 同节点拆开，`key` 放在 `v-for` 模板上。
7. 写入 staging 对应路径，返回逐文件结果 JSON：`{path,status,changes,contract_changes,error}`。`status` 只能是 `done|failed`，失败时必须写清具体行号与原因。

## Pitfalls

- 不要机械替换 `this.`：`<script setup>` 没有 `this`，模板里也不存在 `this`，漏改会在运行时直接报错。
- `filters` 没有等价指令，必须改成函数或 `computed`；继续保留 `filters:` 会让 SFC 编译失败。
- mixin 不能简单改成 `extends`。生命周期合并顺序会变，优先抽成 `useXxx()` composable，并在原组件按原顺序调用。
- `this.$listeners` 在 Vue3 并入 `$attrs`；若组件用 `inheritAttrs: false` 又手工转发，需同时透传 `class` / `style`。
- 事件总线 `new Vue()` 在 Vue3 不可用；`$on` 全部迁移到 Pinia action 或 `mitt`，不要留下悬空监听。
- 深层对象直接改属性在 Vue3 响应式下可行，但替换整个 `reactive` 根对象会丢响应性；用 `Object.assign` 或 `ref` 包一层。
- `v-model` 默认值从 `value` 改为 `modelValue`，漏改会导致输入组件静默不更新。
- 不要顺手格式化整个文件；diff 越大，质量门越难定位真实回归。

## Verification

- `npx vue-tsc --noEmit` 与 `npx vite build` 对该文件或所在 chunk 通过，或明确给出失败信号。
- 组件对外契约对比：props / emits / slots / `v-model` 名称与转换前一致（允许显式列出的破坏性变更）。
- 全文不再出现 `filters:`、`this.$listeners`、`this.$scopedSlots`、`$on(`、`.sync`、`slot-scope`。
- 输出 JSON 可 `json.load`，`status` 与 `changes` 非空，staging 路径与批次清单一一对应。
