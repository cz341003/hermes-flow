import { defineStore } from 'pinia';

export const useUserStore = defineStore('user', {
  state: () => ({
    name: '',
    role: 'guest',
  }),
  getters: {
    isAdmin: (state) => state.role === 'admin',
  },
  actions: {
    async login({ name, role }) {
      const resp = await new Promise((resolve) =>
        setTimeout(() => resolve({ name, role }), 100)
      );
      this.name = resp.name;
      this.role = resp.role;
    },
  },
});