import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '@/utils/auth'

const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', noLayout: true },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '监测大屏', icon: '◈' },
  },
  {
    path: '/events',
    name: 'events',
    component: () => import('@/views/EventsView.vue'),
    meta: { title: '事件中心', icon: '◉' },
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('@/views/TasksView.vue'),
    meta: { title: '工单看板', icon: '▤' },
  },
  {
    path: '/devices',
    name: 'devices',
    component: () => import('@/views/DevicesView.vue'),
    meta: { title: '设备态势', icon: '◎' },
  },
  {
    path: '/reports',
    name: 'reports',
    component: () => import('@/views/ReportsView.vue'),
    meta: { title: '治理报表', icon: '▦' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ---------- 路由守卫：未登录一律回登录页 ----------
router.beforeEach((to) => {
  const isLoginPage = to.name === 'login'
  if (!isLoginPage && !isLoggedIn()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (isLoginPage && isLoggedIn()) {
    return { path: '/' }
  }
  return true
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `${title} · 探海灵眸 SeaSight` : '探海灵眸 SeaSight'
})

export default router
export { routes }
