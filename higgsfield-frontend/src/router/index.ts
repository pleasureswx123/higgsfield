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
          meta: { title: '我的生成', description: '在这里回看和管理你的创作结果。' },
        },
        {
          path: 'elements',
          component: () => import('@/views/MyElementsView.vue'),
          meta: { title: '我的元素', description: '统一管理创作中使用的角色与视觉元素。' },
        },
        {
          path: 'favorites',
          component: () => import('@/views/FavoritesView.vue'),
          meta: { title: '我的收藏', description: '留住值得再次使用的灵感。' },
        },
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
