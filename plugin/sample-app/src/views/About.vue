<template>
  <div class="about">
    <h1>关于</h1>
    <user-card :user="currentUser" />
  </div>
</template>

<script>
import UserCard from '../components/UserCard.vue';

export default {
  name: 'About',
  components: { UserCard },
  props: {
    id: { type: Number, default: 0 },
  },
  computed: {
    currentUser() {
      return { id: this.id || 1, name: '示例用户', role: 'admin' };
    },
  },
};
</script>
