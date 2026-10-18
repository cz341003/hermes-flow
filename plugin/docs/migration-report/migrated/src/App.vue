<template>

  <div id="app">
    <a-layout>
      <a-layout-sider>
        <tree-menu :tree-data="treeData" @select="onSelectNode" />
      </a-layout-sider>
      <a-layout-content>
        <router-view />
      </a-layout-content>
    </a-layout>
  </div>

</template>

<script setup>
import { ref } from 'vue';

const treeData = ref([
        { id: 1, name: '首页', children: [] },
        { id: 2, name: '用户管理', children: [{ id: 21, name: '用户列表' }] },
      ])
function onSelectNode(node) {
      message.info(`选中节点：${node.name}`);
    }
</script>

<style lang="less" scoped>
#app {
  height: 100vh;
}
</style>