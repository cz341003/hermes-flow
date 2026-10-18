// Vue2 全局 mixin：迁移到 Vue3 时应替换为组合式函数（composable）
export default {
  data() {
    return {
      loading: false,
    };
  },
  methods: {
    setLoading(v) {
      this.loading = v;
    },
  },
  beforeDestroy() {
    this.loading = false;
  },
};
