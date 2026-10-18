<template>
  <div class="home">
    <h1>欢迎，{{ user.name || '访客' }}</h1>
    <p>当前角色：{{ user.role | roleText }}</p>
    <hello-world :message="greeting" />
  </div>
</template>

<script>
import { mapState } from 'vuex';
import HelloWorld from '../components/HelloWorld.vue';

export default {
  name: 'Home',
  components: { HelloWorld },
  filters: {
    roleText(role) {
      const map = { admin: '管理员', guest: '访客' };
      return map[role] || role;
    },
  },
  computed: {
    ...mapState('user', ['name', 'role']),
    user() {
      return { name: this.name, role: this.role };
    },
    greeting() {
      return this.name ? `你好，${this.name}` : '你好，访客';
    },
  },
  created() {
    console.log('Home created');
  },
};
</script>

<style lang="less" scoped>
.home {
  padding: 24px;
}
</style>
