---
name: Ant Design Vue 1.x 到 4.x 映射
description: 把 ant-design-vue 1.x 的组件、属性、插槽、图标与事件迁移到 4.x，并处理 ztree 到 a-tree 的替换。
version: 1.0.0
id: vue3-antdv
phases: [transform]
tags: [vue2, vue3, antdv, ant-design-vue, ui, tree, ztree]
---

# Ant Design Vue 1.x 到 4.x 映射

1.x 到 4.x 不只是升级包版本：组件 API、插槽机制、图标体系、表单模型、弹窗可见性都变了。迁移时按「全局注册 -> 组件属性 -> 插槽 -> 事件 -> 图标 -> 主题」顺序推进，避免一次改太多无法定位。

## Procedure

1. 全局装配：`import Antd from 'ant-design-vue'` + `import 'ant-design-vue/dist/reset.css'`，`app.use(Antd)`；删除 `Vue.use(Antd)`。按需引入时改用 `ant-design-vue/es/...` 路径。
2. 组件与属性映射（高频）：
   - `a-modal` / `a-drawer` / `a-dropdown`：`visible` -> `open`；`visibleChange` -> `openChange`。
   - `a-form-model` / `a-form-model-item` -> `a-form` / `a-form-item`；`v-model` 校验模型改为 `:model` + `:rules`，`prop` 保留。
   - `a-tabs` 的 `<a-tab-pane>` 子节点 -> `:items` 数组（或继续用 `a-tab-pane`，但 4.x 推荐 `items`）；`tab` 属性统一为 `key`/`label`。
   - `a-table`：`scopedSlots` / `slot-scope` -> `#bodyCell="{ column, record }"`；`customRender` 仍可用但返回 VNode；`rowKey` 必填。
   - `a-select`：`<a-select-option>` 可用，但推荐 `:options`；`labelInValue` 结构变化。
   - `a-tree`：`treeData` + `fieldNames`；`@check` 参数改为 `(checkedKeys, e)`；`@select` 参数为 `(selectedKeys, e)`；`expandedKeys` 受控需配合 `@expand`。
   - `a-icon` 移除：改用 `@ant-design/icons-vue` 的组件（`<SearchOutlined />`），`type="search"` 写法全部删除。
   - `a-input-group` -> `a-input-group` 仍可用但推荐 `a-space` / `a-input` 组合；`a-button-group` 保留。
   - `a-transfer`、`a-upload`、`a-cascader` 的 `value` / `change` 参数结构按 4.x 文档核对。
3. 插槽迁移：1.x 的 `slot="xxx"` 改为 `#xxx`；`slot-scope` 改为 `#xxx="scope"`；`scopedSlots` 对象改模板插槽。表格 `#bodyCell`、`#headerCell`、`#expandedRowRender` 是重点。
4. 事件迁移：`change` 的 payload 统一为 `(value, option)`；`@click` 在 `a-menu-item` 上仍可用；`a-modal` 的 `@cancel` / `@ok` 不变。
5. 图标：安装 `@ant-design/icons-vue`，逐个替换 `<a-icon type="x" />`；动态图标用 `h(icons[name])`。
6. 表单：`a-form-model` 的 `:model`、`:rules`、`validate` 改为 `a-form` 的 `ref.validate()`；`this.$refs.form.validate()` 在 setup 中 `formRef.value.validate()`。
7. 反馈组件：`this.$message` / `this.$notification` -> 从 `ant-design-vue` 导入 `message` / `notification`；`this.$confirm` -> `Modal.confirm({...})`。
8. ztree -> a-tree 替换：把 `ztree` 的 `setting.data.key` 映射成 `fieldNames: { children: 'children', title: 'name', key: 'id' }`；`check.enable` -> `checkable`；`callback.onCheck` -> `@check`；`expandNode` -> `expandedKeys`；异步加载 `async.load` -> `loadData`；搜索高亮用 `filterTreeNode`。
9. 日期：`moment` 替换为 `dayjs`；`a-date-picker` 的 `value` 从 moment 对象改为 dayjs 对象，`format` 保持。
10. 主题：`modifyVars` 在 4.x 不再推荐，改用 `ConfigProvider` + `theme.token`；Less 变量见 `vue3-less` 技能。

```vue
<!-- 1.x -->
<a-table :columns="columns" :data-source="rows" :scopedSlots="{ bodyCell: 'bodyCell' }">
  <template slot="bodyCell" slot-scope="{ column, record }">
    <a-icon type="edit" @click="edit(record)" />
  </template>
</a-table>

<!-- 4.x -->
<a-table :columns="columns" :data-source="rows" :row-key="r => r.id">
  <template #bodyCell="{ column, record }">
    <EditOutlined @click="edit(record)" />
  </template>
</a-table>
```

## Pitfalls

- `visible` 改 `open` 是高频漏改项：弹窗能打开但关闭按钮无效，或受控状态不更新。
- `a-icon` 组件已不存在，保留 `<a-icon>` 会渲染空标签并报 warning，看起来像「图标丢了」。
- 表格 `scopedSlots` 与 `#bodyCell` 参数名变化：`text, record, index` 改为 `{ text, record, index, column }`。
- `a-form-model` 的 `v-model` 校验写法不迁移，表单会永远校验通过或直接报错。
- ztree 的节点字段不是 `title/key`，必须用 `fieldNames` 映射，否则树渲染为空。
- 受控 `expandedKeys` 不监听 `@expand` 会导致展开后立即收起。
- `message` 静态方法在 setup 外也可用，但 SSR 下会报 `document is not defined`，按需懒调用。
- 4.x 默认 CSS-in-JS 主题，删除 1.x 的 `ant-design-vue/dist/antd.css` 引用，否则样式重复覆盖。

## Verification

- 全仓不再出现 `<a-icon`、`visible=`（针对 modal/drawer/dropdown）、`a-form-model`、`scopedSlots`、`slot-scope`、`moment(`。
- `a-table` 每列有 `dataIndex`/`key`，`rowKey` 已设置，`#bodyCell` 渲染正常。
- 表单必填校验能拦截空值，错误提示位置与 1.x 一致。
- ztree 相关页面全部替换为 `a-tree`，勾选/展开/异步加载/搜索均可用。
- `vite build` 无 antdv 相关 warning，浏览器无 `Failed to resolve component` 警告。
