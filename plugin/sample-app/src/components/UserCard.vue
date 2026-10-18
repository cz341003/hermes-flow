<template>
  <a-card :title="user.name">
    <p>{{ user.role | roleText }}</p>
  </a-card>
</template>

<script>
export default {
  name: 'UserCard',
  props: {
    user: { type: Object, default: () => ({ name: '', role: 'guest' }) },
  },
  filters: {
    roleText(role) {
      return role === 'admin' ? '管理员' : '访客';
    },
  },
};
</script>
