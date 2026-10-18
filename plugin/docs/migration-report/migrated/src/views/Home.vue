<template>

  <div class="home">
    <h1>欢迎，{{ user.name || '访客' }}</h1>
    <p>当前角色：{{ roleText(user.role) }}</p>
    <hello-world :message="greeting" />
  </div>

</template>

<script setup>
import { computed } from 'vue';

const user = computed(() => {return { name: name, role: role };})
const greeting = computed(() => {return name ? `你好，${name}` : '你好，访客';})
function roleText(role) {
      const map = { admin: '管理员', guest: '访客' };
      return map[role] || role;
    }
</script>

<style lang="less" scoped>
.home {
  padding: 24px;
}
</style>