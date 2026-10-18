<template>
  <div class="tree-menu">
    <ul class="ztree" id="treeMenu"></ul>
  </div>
</template>

<script>
import $ from 'jquery';
import 'jquery.ztree';

export default {
  name: 'TreeMenu',
  props: {
    treeData: { type: Array, default: () => [] },
  },
  data() {
    return { zTreeObj: null };
  },
  mounted() {
    this.initTree();
  },
  beforeDestroy() {
    if (this.zTreeObj) {
      this.zTreeObj.destroy();
      this.zTreeObj = null;
    }
  },
  methods: {
    initTree() {
      const setting = {
        data: {
          simpleData: { enable: true, idKey: 'id', pIdKey: 'pid' },
        },
        callback: {
          onClick: (event, treeId, treeNode) => {
            this.$emit('select', treeNode);
          },
        },
      };
      this.zTreeObj = $.fn.zTree.init($('#treeMenu'), setting, this.treeData);
    },
  },
};
</script>
