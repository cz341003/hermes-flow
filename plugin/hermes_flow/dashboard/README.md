# Dashboard build

React Flow 画布由 `@xyflow/react` 提供；React 必须使用宿主实例，不能打进 bundle。

```powershell
cd E:\deepSeek\plugin\hermes_flow\dashboard
npm install
npm run build
```

`build.mjs` 会：

1. 用 esbuild 把 `src/index.js` 打成 `dist/index.js`（IIFE）；
2. 将 `react` / `react/jsx-runtime` / `react-dom` alias 到 `src/shims/*`；
   - `react` → `window.__HERMES_PLUGIN_SDK__.React`（React 19.2.7）
   - `react-dom.createPortal` → fallback（当前不使用 EdgeLabelRenderer/NodeToolbar）
3. 合并 `style.v1.css` + React Flow CSS + `src/extra.css` 为 `dist/style.css`。

产物：`dist/index.js`（约 219KB minified）、`dist/style.css`。
`node_modules/` 不进入 Git / 插件 zip，发布包内是预构建 dist。
