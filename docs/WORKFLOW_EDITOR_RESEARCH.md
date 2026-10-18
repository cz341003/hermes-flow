# 工作流可视化编辑器调研与实现选择

- 日期：2026-10-18
- 结论：**短期用轻量表单编辑（已实现）；中期建议引入 React Flow 做完整节点画布**。

## 1. 市面方案

| 方案 | 特点 | 适合度 |
|---|---|---|
| [React Flow](https://reactflow.dev/ui/templates/workflow-editor) | React 节点画布事实标准；拖拽、连线、Minimap、Controls、自定义节点；官方有 Workflow Editor 模板 | ★★★★★（本项目 Dashboard 是 React SDK） |
| [Vue Flow](https://vueflow.dev/guide/getting-started) | Vue 3 版 React Flow，API 类似；n8n 的节点画布基于 Vue Flow（[n8n canvas](https://deepwiki.com/n8n-io/n8n/6.2-workflow-canvas-and-node-management)） | ★★★★（若宿主是 Vue） |
| [Rete.js](https://retejs.org/docs/) | 可视化编程/节点编辑器框架，强调 socket、数据流、自定义控件 | ★★★☆（更重，偏编程编辑器） |
| Drawflow | 轻量 vanilla JS 节点编辑器 | ★★★（简单但生态/可访问性弱） |
| [Windmill](https://www.windmill.dev/docs/intro) | 低代码工作流平台，内置脚本/流程编辑 | 参考产品形态，不是嵌入库 |

共同交互：左侧节点面板、画布拖拽、端口连线、右侧节点配置、缩放/小地图、保存/运行。

## 2. 本次已实现（无新增依赖）

- 修复模板卡选中态：`hf2-card` 与 `hf2-selected` class 不一致 → 现在青色边框+背景。
- 修复「添加节点」无反应：原实现把新节点放在 `y = 20 + 节点数*70`，克隆 7 节点模板时 y≈510，超出 340px 画布视口并被忽略；现改为 4 列网格位置，并显示“已添加节点”提示。
- 新增 **「节点与连线（表单编辑，无需 JSON）」**：
  - 节点：名称 / phase / agent / skill 直接修改；删除节点自动删关联边。
  - 连线：起点/终点下拉 + 添加；已有连线可改端点或删除。
  - 高级字段（`type`、`batch`、`timeout_s`、`output`）仍用 JSON 编辑。
- 拖拽画布保留；无 `meta.x/y` 时自动 4 列布局。

这样普通用户不写 JSON 也能完成“改节点角色/阶段、增删节点、改依赖边”的常见操作。

## 3. 下一步 React Flow 集成建议

如果要做成 n8n 式体验：

1. 引入 `@xyflow/react`（React Flow 4），由宿主 SDK 提供 React；
2. 自定义节点组件映射 `type: agent_task / batch / quality_gate / human_gate / loop`；
3. 端口连接事件写回 `edges`；拖拽停止时写 `meta.x/y`；
4. 右侧属性面板复用现有表单字段；
5. `onConnect` 时做环检测（React Flow 只画图，业务校验仍在 Registry）；
6. 打包体积会增加（React Flow + d3-zoom），需确认 Dashboard 加载预算。

当前不直接引入的原因：会改变 Dashboard 构建依赖和包体；先以零依赖表单编辑器解决学习成本。
