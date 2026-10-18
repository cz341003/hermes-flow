---
name: Vuex 到 Pinia 迁移
description: 把 Vuex module 拆分为 Pinia store，迁移 getters、actions、持久化与全部 dispatch/commit 调用点。
version: 1.0.0
id: vuex-to-pinia
phases: [transform]
tags: [vue2, vue3, vuex, pinia, state, persistence]
---

# Vuex 到 Pinia 迁移

Pinia 没有 mutations、没有嵌套 module，靠「一个文件一个 store」和组合式函数复用。迁移的核心不是改 API，而是重新划 store 边界并保证所有调用点同时更新。

## Procedure

1. 盘点 `src/store`：列出每个 module 的 `state`、`getters`、`mutations`、`actions`、`namespaced`、跨 module 的 `dispatch`/`commit`、以及 `plugins`（持久化、日志）。
2. 用 `search_files` 找全部调用点：`this.$store`、`mapState`、`mapGetters`、`mapActions`、`mapMutations`、`store.dispatch`、`store.commit`、`useStore()`、路由守卫与工具函数里的 store 引用。
3. 安装并挂载 Pinia：`pnpm add pinia`，在 `main.js` 中 `import { createPinia } from 'pinia'` + `app.use(createPinia())`，删除 `Vue.use(Vuex)` 与 `new Vuex.Store(...)`。
4. 一个 Vuex module 迁移为一个 `defineStore`，保持 `id` 唯一：
   - `state` -> `state: () => ({ ... })`（必须函数，避免共享引用）。
   - `getters` -> `getters`（依赖别的 getter 用 `this`，不要用箭头函数）。
   - `mutations` + `actions` -> 全部合并为 `actions`；原 mutation 的同步赋值直接写进 action。
   - `namespaced` 前缀消失，调用点从 `dispatch('user/login')` 改为 `useUserStore().login()`。
5. 跨 store 调用：在 action 内 `const other = useOtherStore()`；不要在 store 顶层模块作用域调用 `useXxxStore()`（Pinia 尚未安装会报错）。
6. 持久化：Vuex 的 `vuex-persistedstate` 改为 `pinia-plugin-persistedstate`，保持原 `key` 与 `paths`，否则用户本地状态会丢；需要版本迁移时在 `persist` 里加 `serializer` / `afterRestore`。
7. devtools：Pinia 自带 devtools，删除 Vuex 的 devtools 配置；store id 用 kebab-case，方便时间线识别。
8. 组件改造：`computed: { ...mapState(['user']) }` -> `const store = useUserStore()` + `storeToRefs(store)` 解构；直接 `store.user` 也可，但解构必须用 `storeToRefs` 保留响应性。
9. 测试改造：`createTestingPinia` 替代 `createLocalVue` + `Vuex.Store`；每个用例 `setActivePinia(createPinia())`。
10. 输出迁移映射表 `{vuex_module, pinia_store_id, mutations_to_actions, call_sites_changed}` 与验证结果。

```js
// Vuex
export default {
  namespaced: true,
  state: () => ({ token: '', profile: null }),
  getters: { isLogin: s => !!s.token },
  mutations: { SET_TOKEN(s, v) { s.token = v } },
  actions: { async login({ commit }, form) { const { token } = await api.login(form); commit('SET_TOKEN', token) } }
}

// Pinia
export const useUserStore = defineStore('user', {
  state: () => ({ token: '', profile: null }),
  getters: { isLogin: s => !!s.token },
  actions: {
    async login(form) {
      const { token } = await api.login(form)
      this.token = token
    }
  },
  persist: { key: 'user', paths: ['token'] }
})
```

## Pitfalls

- 直接把 mutation 改名成 action 但保留 `commit` 调用会失败；所有 `commit('user/SET_TOKEN')` 必须改成 `store.setToken()` 或 action。
- Pinia 的 `state` 必须是函数；写成对象会在多实例/SSR 下共享状态。
- 解构 `const { token } = useUserStore()` 会丢响应性，必须 `storeToRefs`（action 可以直接解构）。
- 路由守卫、axios 拦截器、工具函数里的 `this.$store` 没有组件实例，必须改成显式传入 store 或 `useUserStore()`（在 pinia 安装后调用）。
- `namespaced` 映射要人工确认：`mapState('user', ['name'])` 迁移后是 `store.name`，不是 `store.user.name`。
- 持久化 `key` 改动会让老用户 token/偏好丢失；迁移期保持 key 并在验收后统一版本化。
- 循环依赖：store A import store B 且 B 又 import A 时，改在 action 内延迟调用 `useBStore()`，不要顶层互相 import 后立即调用。
- `this.$store.state.user.profile` 这类深层引用要改成 `store.profile`，别保留 `state` 层级。

## Verification

- 全仓不再出现 `new Vuex.Store`、`Vue.use(Vuex)`、`commit(`、`dispatch(`、`mapState`、`mapGetters`、`this.$store`。
- 每个 Vuex module 都有对应 Pinia store，且 `id` 唯一；跨 module 依赖通过 action 内调用完成。
- `useUserStore()` 在组件 setup 顶层调用；解构使用 `storeToRefs`。
- `createPinia()` 已挂载，刷新页面后无 `getActivePinia` 报错，devtools 能看到 store。
- 持久化 key 与迁移前一致；关键状态（token、主题、语言）刷新后保留。
- 相关 Vitest 用例通过，浏览器验证覆盖登录/退出/列表读取。
