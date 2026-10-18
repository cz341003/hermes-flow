const state = {
  name: '',
  role: 'guest',
};

const getters = {
  isAdmin: (state) => state.role === 'admin',
};

const mutations = {
  SET_NAME(state, name) {
    state.name = name;
  },
  SET_ROLE(state, role) {
    state.role = role;
  },
};

const actions = {
  async login({ commit }, { name, role }) {
    // 模拟登录接口
    const resp = await new Promise((resolve) =>
      setTimeout(() => resolve({ name, role }), 100)
    );
    commit('SET_NAME', resp.name);
    commit('SET_ROLE', resp.role);
  },
};

export default {
  namespaced: true,
  state,
  getters,
  mutations,
  actions,
};
