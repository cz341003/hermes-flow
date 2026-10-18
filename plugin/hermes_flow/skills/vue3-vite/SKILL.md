---
name: Webpack 到 Vite 配置迁移
description: 把 vue-cli 与 webpack 配置迁移到 Vite，覆盖别名、代理、环境变量、静态资源与构建产物。
version: 1.0.0
id: vue3-vite
phases: [transform]
tags: [vue2, vue3, vite, webpack, build, config]
---

# Webpack 到 Vite 配置迁移

Vite 不是 webpack 的配置翻译器：它用 ESM 原生加载、以 `index.html` 为入口、环境变量前缀不同、`require` 不复存在。迁移顺序是「入口 -> 插件 -> 别名/代理 -> 环境变量 -> 构建」，每步都可单独验证。

## Procedure

1. 盘点旧构建面：`vue.config.js`（`publicPath`、`devServer`、`css.loaderOptions`、`configureWebpack`、`chainWebpack`）、`babel.config.js`、`.env*`、`public/index.html`、`src/main.js`。
2. 新建 `vite.config.ts`：
   - `import vue from '@vitejs/plugin-vue'`，`plugins: [vue()]`。
   - `resolve.alias` 把 `@` 映射到 `fileURLToPath(new URL('./src', import.meta.url))`，其余别名照抄旧配置；Vite 配置是 ESM，不能直接用 `__dirname`。
   - `resolve.extensions` 默认 `['.mjs','.js','.ts','.jsx','.tsx','.json']`，需要 `.vue` 时显式加。
   - `base` 对应旧 `publicPath`；`build.outDir` 默认 `dist`。
3. 迁移入口：把 `public/index.html` 移到项目根 `index.html`，删除 `%PUBLIC_URL%`，加 `<script type="module" src="/src/main.js"></script>`；`public/` 下的静态文件仍按原路径引用。
4. 迁移环境变量：`process.env.VUE_APP_XXX` -> `import.meta.env.VITE_XXX`，`.env` 中前缀改 `VITE_`；`process.env.NODE_ENV` -> `import.meta.env.MODE` / `import.meta.env.PROD` / `import.meta.env.DEV`。注意 Vite 只暴露 `VITE_` 前缀变量。
5. 迁移 dev server：`devServer.proxy` -> `server.proxy`（`changeOrigin`、`rewrite` 保持一致）；`devServer.port/host/https` -> `server.*`；需要局域网访问时 `host: '0.0.0.0'`。
6. 替换 webpack-only 能力：
   - `require.context('./dir', true, /\.vue$/)` -> `import.meta.glob('./dir/**/*.vue', { eager: true })`。
   - `require('./x.json')` -> `import x from './x.json'`。
   - `url-loader` / `file-loader` 的 `?inline` 等 -> `?url` / `?raw` / `?inline` 后缀。
   - `DefinePlugin` -> `define`；`ProvidePlugin` -> `import` 或用 `optimizeDeps` 预构建。
   - `webpackChunkName` 魔法注释删除，`import()` 自动分包。
7. 迁移 CSS/Less/Sass：`css.loaderOptions.less` -> `css.preprocessorOptions.less`，`additionalData` 注入全局变量；细节见 `vue3-less` 技能。
8. 迁移构建配置：`configureWebpack.optimization.splitChunks` -> `build.rollupOptions.output.manualChunks`；`productionSourceMap` -> `build.sourcemap`；`transpileDependencies` 通常可删除（Vite 按需转译）。
9. 清理 webpack 依赖：移除 `webpack`、`vue-loader`、`vue-cli-service` 相关包与 `babel.config.js`（除非测试需要）；`package.json` scripts 改为 `vite` / `vite build` / `vite preview`。
10. 输出迁移说明：配置 diff、环境变量改名清单、删除的 loader/plugin、仍需保留的兼容项。

```ts
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    extensions: ['.mjs', '.js', '.ts', '.vue', '.json']
  },
  server: {
    host: '127.0.0.1',
    port: 4173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') }
    }
  },
  css: { preprocessorOptions: { less: { additionalData: '@import "@/styles/variables.less";' } } },
  build: { sourcemap: false, rollupOptions: { output: { manualChunks: { vendor: ['vue', 'vue-router', 'pinia'] } } } }
})
```

## Pitfalls

- Vite 配置是 ESM，`__dirname` / `require` 不存在；用 `fileURLToPath(new URL(...))` 或 `import.meta.url`。
- 环境变量不加 `VITE_` 前缀不会注入浏览器端，页面里会读到 `undefined`，但构建不报错。
- `public/index.html` 放错位置会导致 404 或脚本不加载；Vite 的入口必须是项目根 `index.html`。
- `require.context` 是 webpack 专属；漏改会在浏览器报 `require is not defined`。
- 别名只配了 `resolve.alias` 却漏了 Less 的 `@import` 路径，样式里的 `@/styles` 仍会解析失败。
- 代理只在 dev server 生效，生产环境仍需网关/Nginx 配置，不能把 `/api` 相对路径当成已解决。
- 删除 `babel.config.js` 前确认没有自定义插件（如按需引入、装饰器）；否则运行时报语法错误。
- `build.rollupOptions` 的手动分包写错会产生循环 chunk 警告，先验证再优化。

## Verification

- `vite build` 成功，`dist/index.html` 引用带 hash 的 JS/CSS，`dist/assets` 无缺失。
- `vite` dev server 启动后首页、深链、静态资源均 200；代理接口返回与旧 devServer 一致。
- 全仓不再出现 `process.env.VUE_APP_`、`require.context`、`require(`、`module.exports`（配置文件除外）。
- `import.meta.env.VITE_*` 在构建产物中被正确替换，敏感变量没有被打进前端。
- 路由懒加载 chunk 全部生成，浏览器 network 无 404。
