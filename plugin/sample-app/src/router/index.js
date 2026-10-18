import Vue from 'vue';
import VueRouter from 'vue-router';
import Home from '../views/Home.vue';
import UserList from '../views/UserList.vue';
import About from '../views/About.vue';

Vue.use(VueRouter);

const routes = [
  { path: '/', redirect: '/home' },
  { path: '/home', name: 'home', component: Home },
  { path: '/users', name: 'users', component: UserList },
  { path: '/about', name: 'about', component: About },
  { path: '*', redirect: '/home' },
];

const router = new VueRouter({
  mode: 'history',
  base: process.env.BASE_URL,
  routes,
});

router.beforeEach((to, from, next) => {
  document.title = to.meta.title || 'Sample Vue2 App';
  next();
});

export default router;
