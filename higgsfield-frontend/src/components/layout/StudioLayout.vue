<script setup lang="ts">
import { ref, useTemplateRef, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Sheet, SheetContent, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { SidebarProvider, Sidebar, SidebarHeader, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarMenu, SidebarMenuItem, SidebarMenuButton } from '@/components/ui/sidebar'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  IconHome,
  IconFolder,
  IconMenu2,
  IconLogout,
} from '@tabler/icons-vue'
import { ElMessage } from 'element-plus'
import { useSidebarProjects } from '@/composables/useSidebarProjects'
import SidebarProjectActions from '@/components/projects/SidebarProjectActions.vue'
import { useProjectOrder } from '@/composables/useProjectOrder'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/shared/ThemeToggle.vue'
import NightmareLogo from '@/components/shared/NightmareLogo.vue'
import Button from '@/components/ui/Button.vue'
const auth = useAuthStore(),
  router = useRouter(),
  route = useRoute()
const { user } = storeToRefs(auth)
const sidebarProjects = useSidebarProjects()
const projectOrder = useProjectOrder(sidebarProjects.projects)
const mobileOpen = ref(false),
  leaving = ref(false)
const desktopHost = useTemplateRef<HTMLElement>('desktopHost')
const mobileHost = useTemplateRef<HTMLElement>('mobileHost')
const isMobile = useMediaQuery('(max-width: 760px)')
watch(isMobile, () => { mobileOpen.value = false })
function closeMobileNavigation(event: MouseEvent) {
  if (isMobile.value && (event.target as Element).closest('.project-local-navigation .nav-link, .folder-tree-label:not(.folder-add)')) mobileOpen.value = false
}
const links = [
  { path: '/home', label: '首页', icon: IconHome },
]
async function signOut() {
  leaving.value = true
  try {
    await auth.signOut()
  } catch {
    ElMessage.warning('本地已退出，服务端会话撤销失败')
  } finally {
    leaving.value = false
    await router.replace('/login')
  }
}
</script>
<template>
  <SidebarProvider :keyboard-shortcut="false" :default-open="true" class="studio-shell" @keydown.esc="mobileOpen = false">
    <div ref="desktopHost" class="studio-sidebar-host"></div>
    <Sheet :open="isMobile && mobileOpen" @update:open="mobileOpen = $event">
      <SheetContent side="left" class="studio-mobile-sheet">
        <SheetTitle class="sr-only">工作空间导航</SheetTitle>
        <SheetDescription class="sr-only">项目导航、文件夹和账号操作</SheetDescription>
        <div ref="mobileHost" class="studio-mobile-sidebar-host"></div>
      </SheetContent>
    </Sheet>
    <!-- 移动同一侧栏节点，保留项目与文件夹的 Teleport 挂载点。 -->
    <Teleport :to="mobileHost || desktopHost" :disabled="!desktopHost">
    <Sidebar collapsible="none" class="sidebar" :class="{ 'is-open': mobileOpen }" aria-label="工作空间侧栏" @click="closeMobileNavigation">
      <SidebarHeader class="studio-sidebar-header">
      <RouterLink to="/home" class="brand" @click="mobileOpen = false"
        ><NightmareLogo class="sidebar-brand-logo" /></RouterLink
      >
      <ThemeToggle class="sidebar-theme-toggle" />
      </SidebarHeader>
      <SidebarContent class="studio-sidebar-content">
      <nav aria-label="主导航"><SidebarMenu>
        <SidebarMenuItem v-for="link in links" :key="link.path"><SidebarMenuButton as-child :is-active="route.path === link.path"><RouterLink
          :to="link.path"
          class="nav-link"
          @click="mobileOpen = false"
          ><component :is="link.icon" :size="20" /><span>{{ link.label }}</span></RouterLink
        ></SidebarMenuButton></SidebarMenuItem>
      </SidebarMenu></nav>
      <div v-show="route.params.id" id="project-sidebar-navigation"></div>
      <SidebarGroup class="sidebar-projects" :class="{ 'in-project': route.params.id }">
        <SidebarGroupLabel v-if="!route.params.id" class="section-label">项目空间</SidebarGroupLabel>
        <nav v-if="!route.params.id" class="sidebar-project-list" aria-label="我参与的项目列表">
          <SidebarMenu>
            <SidebarMenuItem v-for="project in sidebarProjects.projects.value" :key="project.id"
              :draggable="!projectOrder.locked.orderLocked && !sidebarProjects.loading.value" :class="{ 'project-drag-over': projectOrder.over.value === project.id, 'project-dragging': projectOrder.dragging.value === project.id }"
              @dragstart="projectOrder.start($event, project.id)" @dragend="projectOrder.end" @dragover.prevent="projectOrder.over.value = project.id" @dragleave="projectOrder.over.value = ''" @drop.prevent="projectOrder.drop($event, project.id)">
              <SidebarMenuButton as-child><RouterLink :to="`/projects/${project.id}`" :draggable="false" class="sidebar-project-link" :title="`${project.name} · 拖动排序，或按 Alt + 上下方向键`" @click="mobileOpen = false" @keydown.alt.up.prevent="projectOrder.keyboard(project.id, -1)" @keydown.alt.down.prevent="projectOrder.keyboard(project.id, 1)">
                <span class="sidebar-project-icon"><IconFolder :size="18" /></span><span>{{ project.name }}</span>
              </RouterLink></SidebarMenuButton>
              <SidebarProjectActions :project="project" />
            </SidebarMenuItem>
          </SidebarMenu>
          <span v-if="sidebarProjects.loading.value && !sidebarProjects.projects.value.length" class="sidebar-project-hint" role="status">加载中…</span>
          <Button v-else-if="sidebarProjects.error.value" variant="ghost" class="sidebar-project-hint" @click="sidebarProjects.load">加载失败，重试</Button>
          <span v-else-if="!sidebarProjects.projects.value.length" class="sidebar-project-hint">暂无可显示的项目</span>
          <span v-if="projectOrder.saving.value" class="sidebar-project-hint" role="status">正在保存顺序…</span>
          <div v-else-if="projectOrder.error.value" class="sidebar-project-hint" role="alert">{{ projectOrder.error.value }}<Button v-if="projectOrder.locked.orderLocked" variant="ghost" @click="projectOrder.save">重试保存顺序</Button></div>
        </nav>
        <div v-show="route.params.id" id="project-sidebar-tree"></div>
      </SidebarGroup>
      <div v-show="route.params.id" id="project-sidebar-management"></div>
      </SidebarContent>
      <SidebarFooter class="sidebar-bottom">
        <div class="account-row">
          <span class="avatar">{{
            (user?.user.nickName || user?.user.userName || 'U').slice(0, 1)
          }}</span>
          <div class="account-name">
            <strong>{{ user?.user.nickName || user?.user.userName }}</strong
            ><small>制作工作空间</small>
          </div>
          <Button
            variant="ghost"
            class="icon-button"
            aria-label="退出登录"
            :disabled="leaving"
            @click="signOut"
            ><IconLogout :size="19"
          /></Button>
        </div>
      </SidebarFooter>
    </Sidebar>
    </Teleport>
    <main class="studio-main">
      <header class="workspace-header">
        <Button
          class="mobile-toggle icon-button"
          variant="ghost"
          aria-label="打开导航"
          @click="mobileOpen = true"
          ><IconMenu2 :size="21" /></Button
        ><span>{{ route.meta.title }}</span
        ><span class="workspace-label">制作工作空间</span>
      </header>
      <div v-if="user?.isDefaultModifyPwd || user?.isPasswordExpired" class="password-notice">
        请前往管理平台个人中心修改初始或过期密码。
      </div>
      <RouterView v-slot="{ Component }"
        ><KeepAlive><component :is="Component" :key="route.path" /></KeepAlive
      ></RouterView>
    </main>
  </SidebarProvider>
</template>

<style scoped>
.studio-sidebar-header { flex-direction:row; align-items:center; padding:1px 7px 18px; gap:8px; }
.studio-sidebar-header .brand { flex:1; min-width:0; padding:0; font-size:14px; gap:8px; }
.studio-sidebar-header .sidebar-brand-logo { display:block; width:100%; max-width:172px; height:auto; flex-shrink:1; color:var(--foreground); }
.studio-sidebar-header .sidebar-theme-toggle { flex:0 0 30px; width:30px; height:30px; min-height:0; padding:0; color:var(--muted-foreground); }
.studio-sidebar-content { gap:0; overflow:hidden; }
.sidebar-projects { padding:0; }
.sidebar-projects:not(.in-project) { flex-shrink:0; }
.sidebar-projects .section-label { height:auto; flex-shrink:0; padding:0 12px 12px; }
.sidebar-bottom { padding:0; gap:0; border-top:1px solid var(--border); }
.sidebar [data-sidebar="menu"] { margin:0; padding:0; list-style:none; gap:0; }
.sidebar .nav-link { height:auto; min-height:42px; }

.sidebar-project-list { flex-shrink:0; display:flex; flex-direction:column; gap:4px; margin-top:8px; max-height:40vh; overflow-y:auto; }
.sidebar-project-link { flex-shrink:0; display:flex; align-items:center; gap:10px; min-height:40px; padding:5px 40px 5px 10px; border-radius:8px; color:var(--foreground); text-decoration:none; font-size:13px; font-weight:600; }
.sidebar-project-link > span:last-child { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.sidebar-project-icon { display:grid; place-items:center; flex:0 0 28px; height:28px; border-radius:8px; color:var(--muted-foreground); background:var(--surface-hover); }
.sidebar-project-link:hover { background:var(--surface-hover); }
.project-drag-over { outline:1px solid var(--primary); outline-offset:-1px; border-radius:8px; }
.project-dragging { opacity:0.5; }
.sidebar-project-link:focus-visible { outline:2px solid var(--focus); outline-offset:-2px; }
.sidebar-project-hint { padding:8px 10px; font-size:12px; color:var(--muted-foreground); }
</style>

<style scoped>
.studio-sidebar-content > nav { flex-shrink:0; margin-bottom:8px; }
#project-sidebar-navigation { flex-shrink:0; }
.sidebar-projects.in-project { margin-top:14px; }
#project-sidebar-management { flex-shrink:0; padding-top:4px; }
</style>
