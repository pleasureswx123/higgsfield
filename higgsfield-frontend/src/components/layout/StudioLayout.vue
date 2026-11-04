<script setup lang="ts">
import { ref, useTemplateRef, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Sheet, SheetContent, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { SidebarProvider, Sidebar, SidebarHeader, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarMenu, SidebarMenuItem, SidebarMenuButton } from '@/components/ui/sidebar'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  IconHome,
  IconSparkles,
  IconBox,
  IconFolder,
  IconMenu2,
  IconLogout,
  IconChevronRight,
} from '@tabler/icons-vue'
import { ElMessage } from 'element-plus'
import { useSidebarProjects } from '@/composables/useSidebarProjects'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/shared/ThemeToggle.vue'
import Button from '@/components/ui/Button.vue'
const auth = useAuthStore(),
  router = useRouter(),
  route = useRoute()
const { user } = storeToRefs(auth)
const sidebarProjects = useSidebarProjects()
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
  { path: '/generations', label: '我的生成记录', icon: IconSparkles },
  { path: '/elements', label: '我创建的元素', icon: IconBox },
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
      <RouterLink v-if="!route.params.id" to="/home" class="brand"
        ><img src="/brand-mark.svg" width="32" height="32" alt="Higgsfield 制作平台" /><span>Higgsfield <small>STUDIO</small></span></RouterLink
      >
      </SidebarHeader>
      <SidebarContent class="studio-sidebar-content">
      <nav v-if="!route.params.id" aria-label="主导航"><SidebarMenu>
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
        <SidebarMenu v-if="!route.params.id">
          <SidebarMenuItem><SidebarMenuButton as-child :is-active="route.path === '/projects'"><RouterLink to="/projects" class="nav-link" @click="mobileOpen = false">
            <IconFolder :size="20" /><span>我的项目</span><IconChevronRight class="push-right" :size="15" />
          </RouterLink></SidebarMenuButton></SidebarMenuItem>
        </SidebarMenu>
        <nav v-if="!route.params.id" class="sidebar-project-list" aria-label="我的项目列表">
          <SidebarMenu>
            <SidebarMenuItem v-for="project in sidebarProjects.projects.value" :key="project.id">
              <SidebarMenuButton as-child><RouterLink :to="`/projects/${project.id}`" class="sidebar-project-link" :title="project.name" @click="mobileOpen = false">
                <span class="sidebar-project-icon"><IconFolder :size="18" /></span><span>{{ project.name }}</span>
              </RouterLink></SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          <span v-if="sidebarProjects.loading.value && !sidebarProjects.projects.value.length" class="sidebar-project-hint" role="status">加载中…</span>
          <Button v-else-if="sidebarProjects.error.value" variant="ghost" class="sidebar-project-hint" @click="sidebarProjects.load">加载失败，重试</Button>
          <RouterLink v-if="sidebarProjects.hasMore.value" to="/projects" class="sidebar-project-hint" @click="mobileOpen = false">查看全部项目</RouterLink>
        </nav>
        <div v-show="route.params.id" id="project-sidebar-tree"></div>
      </SidebarGroup>
      </SidebarContent>
      <SidebarFooter class="sidebar-bottom">
        <div class="theme-row"><span>外观</span><ThemeToggle /></div>
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
.studio-sidebar-header { padding:0; gap:0; }
.studio-sidebar-header .brand { padding:1px 7px 25px; font-size:17px; }
.studio-sidebar-content { gap:0; overflow:hidden; }
.sidebar-projects { padding:0; }
.sidebar-projects:not(.in-project) { flex-shrink:0; }
.sidebar-projects .section-label { height:auto; flex-shrink:0; padding:0 12px 12px; }
.sidebar-bottom { padding:0; gap:0; }
.sidebar [data-sidebar="menu"] { margin:0; padding:0; list-style:none; gap:0; }
.sidebar .nav-link { height:auto; min-height:42px; }

.sidebar-project-list { flex-shrink:0; display:flex; flex-direction:column; gap:4px; margin-top:8px; max-height:40vh; overflow-y:auto; }
.sidebar-project-link { flex-shrink:0; display:flex; align-items:center; gap:10px; min-height:40px; padding:5px 10px; border-radius:8px; color:var(--foreground); text-decoration:none; font-size:13px; font-weight:600; }
.sidebar-project-link > span:last-child { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.sidebar-project-icon { display:grid; place-items:center; flex:0 0 28px; height:28px; border-radius:8px; color:var(--muted-foreground); background:var(--surface-hover); }
.sidebar-project-link:hover { background:var(--surface-hover); }
.sidebar-project-link:focus-visible { outline:2px solid var(--focus); outline-offset:-2px; }
.sidebar-project-hint { padding:8px 10px; font-size:12px; color:var(--muted-foreground); }
</style>
