<template>
  <a-tree
    :tree-data="treeData"
    :field-names="{ children: 'children', title: 'name', key: 'id' }"
    @select="onSelect"
  />
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue';

defineProps({
  treeData: { type: Array, default: () => [] },
});

const emit = defineEmits(['select']);

function onSelect(keys, info) {
  emit('select', info.node);
}

onBeforeUnmount(() => {});
</script>