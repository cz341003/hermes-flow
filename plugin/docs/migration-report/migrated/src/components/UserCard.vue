<template>

  <a-card :title="user.name">
    <p>{{ roleText(user.role) }}</p>
  </a-card>

</template>

<script setup>

defineProps({user: { type: Object, default: () => ({ name: '', role: 'guest' }) },})
function roleText(role) {
      return role === 'admin' ? '管理员' : '访客';
    }
</script>