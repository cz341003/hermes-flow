---
name: Vue Router 3 到 4 迁移
description: 把 Vue Router 3 的实例、路由表、守卫与编程式导航迁移到 Vue Router 4 的新 API。
version: 1.0.0
id: vue3-router4
phases: [transform]
tags: [vue2, vue3, router, vue-router, navigation-guard, lazy-load]
---

# Vue Router 3 到 4 迁移

Router 4 的破坏性变化集中在四类：创建方式、通配符、守卫返回值、编程式导航返回值。路由表本身大多能复用，但漏改通配符和 `next()` 会在运行时静默失效。

## Procedure

1. 盘点路由入口：`src/router/index.js`、`routes.js`、权限守卫、动态路由（`router.addRoutes`）、`router.beforeEach` / `afterEach`、`beforeRouteEnter` 组件内守卫。
2. 创建方式迁移：
   - `new VueRouter({ mode: 'history', routes })` -> `createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })`。
   - hash 模式 -> `createWebHashHistory()`；抽象模式 -> `createMemoryHistory()`（SSR/测试）。
   - `Vue.use(VueRouter)` 删除，改为 `app.use(router)`。
3. 路由表迁移：
   - 通配符 `path: '*'` -> `path: '/:pathMatch(.*)*'`；`path: '/404'` 兜底仍可保留，但必须最后注册。
   - `component: () => import('@/views/X.vue')` 保持懒加载；确认 Vite 能解析别名。
   - `meta`、`props`、`children`、`redirects` 结构不变；`redirect` 函数参数从 `to` 改为 `to`（仍可用）。
   - `base` 从构造参数移到 `createWebHistory(base)`。
4. 守卫迁移：
   - `router.beforeEach((to, from, next) => { ... next('/login') })` -> `return '/login'` 或 `return { name: 'login' }`。
   - 放行：`next()` -> `return true`（或直接 return）；取消：`return false`；抛错：`throw new Error(...)`。
   - `next(vm => ...)` 形式删除，改用 `await` 或 `afterEach`。
   - `beforeRouteEnter(to, from, next)` 中访问 `this` 的写法删除，改用 `next(vm => ...)`（该形式仍保留）或 setup 中 `onBeforeRouteEnter`。
5. 编程式导航：
   - `router.push(...)` / `replace(...)` 返回 Promise；未捕获的重复导航会抛 `NavigationDuplicated`，加 `catch(() => {})` 或判断 `to.name !== from.name`。
   - `router.push({ path, query, params })` 中 `params` 与 `path` 不能同时用，改 `name` 或改用 query。
   - `router.match` -> `router.resolve`；`router.addRoutes` -> `router.addRoute`（每次一条）。
6. 组件内 API：`this.$router` / `this.$route` -> `useRouter()` / `useRoute()`；`this.$route.params.id` 继续可用，但 setup 中需 `const route = useRoute()`。
7. `<router-view>` / `<router-link>` 基本兼容；`<router-link :to>` 的事件、`exact` 属性删除（用 `router-link-exact-active` 类或自定义 active 逻辑）。
8. 输出迁移说明：路由表 diff、守卫改写列表、动态路由注册点、仍依赖 `next` 的位置。

```js
// Vue Router 3
const router = new VueRouter({
  mode: 'history',
  routes: [
    { path: '/users/:id', component: UserDetail, meta: { auth: true } },
    { path: '*', redirect: '/404' }
  ]
})
router.beforeEach((to, from, next) => {
  if (to.meta.auth && !store.state.user.token) next('/login')
  else next()
})

// Vue Router 4
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/users/:id', component: () => import('@/views/UserDetail.vue'), meta: { auth: true } },
    { path: '/:pathMatch(.*)*', redirect: '/404' }
  ]
})
router.beforeEach((to) => {
  if (to.meta.auth && !useUserStore().token) return { name: 'login', query: { redirect: to.fullPath } }
  return true
})
```

## Pitfalls

- 保留 `next()` 混用 `return` 会导致守卫执行两次或不放行；Router 4 里统一用返回值，别再传 `next` 参数。
- `path: '*'` 不迁移会匹配不到未定义路由，表现为白屏或控制台警告，而不是 404 页面。
- `params` 与 `path` 同时出现在 `router.push` 时 Router 4 直接忽略 `params`；详情页会拿不到 id。
- `router.addRoutes` 已删除；动态权限路由要循环 `routes.forEach(r => router.addRoute(r))`，并在退出登录时 `removeRoute`。
- `beforeRouteEnter` 里用 `this` 在 Vue3 仍不可用；只有 `next(vm => ...)` 能拿到实例。
- 未捕获的导航 Promise rejection 在测试中会变成失败用例；统一加 `.catch`。
- `scrollBehavior` 的 `savedPosition` 仅在使用浏览器前进/后退时存在，不要假设总有值。
- 路由懒加载路径写错会返回 404 chunk，浏览器表现为白屏；用 `vite build` 提前暴露。

## Verification

- 全仓不再出现 `new VueRouter`、`Vue.use(VueRouter)`、`mode: 'history'`、`path: '*'`、`next(`（`nextTick` 除外）。
- `router.beforeEach` 与组件内守卫全部使用返回值语义，没有 `next` 参数。
- 直接访问深链、刷新页面、前进后退、未匹配路由均有正确页面。
- 动态路由在登录后注册、退出后移除，重复登录不重复注册。
- `vite build` 通过，路由 chunk 全部生成；浏览器控制台无 Router 警告。
