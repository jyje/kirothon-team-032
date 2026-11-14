import { createRouter, createWebHistory } from 'vue-router'
import { auth, refreshAuth } from './auth'
import LoginView from './views/LoginView.vue'
import SessionDetailView from './views/SessionDetailView.vue'
import SessionsView from './views/SessionsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/sessions' },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/sessions', name: 'sessions', component: SessionsView },
    { path: '/sessions/:id', name: 'session', component: SessionDetailView },
  ],
})

router.beforeEach(async (to) => {
  if (!auth.ready) await refreshAuth()
  if (!auth.authenticated && to.name !== 'login') return { name: 'login' }
  if (auth.authenticated && to.name === 'login') return { name: 'sessions' }
})
