import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue') },
    {
      path: '/',
      component: () => import('@/components/layout/StudioLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: 'usage', redirect: '/home' },
        { path: '', redirect: '/home' },
        { path: 'home', component: () => import('@/views/HomeView.vue'), meta: { title: '首页' } },
        {
          path: 'projects',
          name: 'projects',
          component: () => import('@/views/ProjectsView.vue'),
          meta: { title: '我的项目', description: '将你的创意、素材与团队汇聚在一个项目中。' },
        },
        {
          path: 'projects/:id',
          name: 'project-detail',
          component: () => import('@/views/ProjectDetailView.vue'),
          meta: { title: '项目详情' },
        },
        {
          path: 'generations',
          component: () => import('@/views/GenerationsView.vue'),
          meta: { title: '我的生成记录', description: '跨项目查看本人发起的 AI 生成任务与结果。' },
        },
        {
          path: 'elements',
          component: () => import('@/views/MyElementsView.vue'),
          meta: { title: '我创建的元素', description: '跨项目查看本人创建的角色、场景、道具等可复用元素。' },
        },
        { path: 'favorites', redirect: '/home' },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restoreSession()
  if (to.meta.requiresAuth && !auth.isAuthenticated)
    return { path: '/login', query: { redirect: to.fullPath } }
  if (to.path === '/login' && auth.isAuthenticated) return '/home'
})
router.afterEach((to) => {
  document.title = `${to.meta.title || '登录'} · Higgsfield Studio`
})
