# 工作流可视化编辑器调研与实现

- 日期：2026-10-18
- 结论：**已集成 React Flow，完整可视化连线**；同时保留表单/JSON 作为高级编辑。

## 1. 市面方案

| 方案 | 特点 | 结论 |
|---|---|---|
| [React Flow](https://reactflow.dev/ui/templates/workflow-editor) | React 节点画布事实标准；拖拽、端口连线、Minimap、Controls、自定义节点；官方 Workflow Editor 模板 | **已采用** |
| [Vue Flow](https://vueflow.dev/guide/getting-started) | Vue 3 版 React Flow；n8n 的节点画布基于 Vue Flow（[n8n canvas](https://deepwiki.com/n8n-io/n8n/6.2-workflow-canvas-and-node-management)） | 若宿主是 Vue 时首选 |
| [Rete.js](https://retejs.org/docs/) | 可视化编程/节点编辑器框架，socket/数据流能力更强 | 偏重，暂不采用 |
| Drawflow | 轻量 vanilla 节点编辑器 | 生态/可访问性弱 |
| [Windmill](https://www.windmill.dev/docs/intro) | 低代码工作流平台 | 产品形态参考 |

## 2. 本次实现

- 引入 `@xyflow/react@12.12.0`；
- 通过 esbuild alias 将 `react` / `react/jsx-runtime` / `react-dom` 指向**宿主 React 19.2.7**，避免双 React：
  - `react` → 宿主 `window.__HERMES_PLUGIN_SDK__.React`
  - `react/jsx-runtime` → 用宿主 React.createElement 实现
  - `react-dom.createPortal` → 安全 fallback（当前不使用 EdgeLabelRenderer/NodeToolbar）
- 自定义节点：agent_task / batch / quality_gate / human_gate / loop 统一显示 name/phase/agent；
- 交互：
  - 画布拖拽节点；
  - 从右侧 source 端口拉到左侧 target 端口建立连线；
  - Delete 键 / 工具栏删除选中节点；
  - 添加节点自动放到可见网格；
  - Controls / MiniMap / Background；
  - 节点位置写回 `node.meta.x/y`；
  - 连线写回 `edges`；
  - `保存工作流` 持久化。
- 保留表单编辑 + JSON 编辑：
  - 表单改 name/phase/agent/skill、增删节点、下拉增删连线；
  - JSON 改 `type`/`batch`/`timeout_s`/`output` 等高级字段。

## 3. 验证

- React Flow 画布：7 节点、7 边、2 个端口/节点；
- 添加节点：7 → 8；
- 端口拉线：7 → 8 条边；
- 模板卡选中态：青色边框/背景；
- console errors：0；
- Dashboard bundle：约 219 KB（React Flow 增加约 185 KB minified）；
- 宿主 React 19.2.7 兼容。

## 4. 取舍

- React Flow 增加 bundle 体积（约 185KB minified），换来完整可视化连线/缩放/小地图；
- 当前不使用 React Flow 的 EdgeLabelRenderer/NodeToolbar，因此宿主无需暴露 ReactDOM；
- 高级 DSL 字段（batch 配置、条件、timeout）仍建议表单化，后续可做右侧属性面板。
