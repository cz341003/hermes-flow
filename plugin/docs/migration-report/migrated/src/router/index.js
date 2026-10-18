import { createRouter, createWebHistory } from 'vue-router';
import Home from '../views/Home.vue';
import UserList from '../views/UserList.vue';
import About from '../views/About.vue';

const routes = [
  { path: '/', redirect: '/home' },
  { path: '/home', name: 'home', component: Home },
  { path: '/users', name: 'users', component: UserList },
  { path: '/about', name: 'about', component: About },
  { path: '/:pathMatch(.*)*', redirect: '/home' },
];

const router = createRouter({
  history: createWebHistory(),
  base: process.env.BASE_URL,
  routes,
});

router.beforeEach((to) => {
  document.title = to.meta.title || 'Sample Vue2 App';
  });

export default router;
