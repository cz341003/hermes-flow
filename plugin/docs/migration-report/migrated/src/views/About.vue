<template>

  <div class="about">
    <h1>关于</h1>
    <user-card :user="currentUser" />
  </div>

</template>

<script setup>
import { computed } from 'vue';

defineProps({id: { type: Number, default: 0 },})
const currentUser = computed(() => {return { id: id || 1, name: '示例用户', role: 'admin' };})
</script>