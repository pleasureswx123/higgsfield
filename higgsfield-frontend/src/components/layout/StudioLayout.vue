<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  IconAperture,
  IconHome,
  IconSparkles,
  IconBox,
  IconHeart,
  IconFolder,
  IconMenu2,
  IconLogout,
  IconChevronRight,
  IconX,
  IconChartBar,
} from '@tabler/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/shared/ThemeToggle.vue'
import Button from '@/components/ui/Button.vue'
const auth = useAuthStore(),
  router = useRouter(),
  route = useRoute()
const { user } = storeToRefs(auth)
const mobileOpen = ref(false),
  leaving = ref(false)
const links = [
  { path: '/usage', label: '我的用量', icon: IconChartBar },
  { path: '/home', label: '首页', icon: IconHome },
  { path: '/generations', label: '我的生成', icon: IconSparkles },
  { path: '/elements', label: '我的元素', icon: IconBox },
  { path: '/favorites', label: '我的收藏', icon: IconHeart },
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
  <div class="studio-shell" @keydown.esc="mobileOpen = false">
    <button
      v-if="mobileOpen"
      class="sidebar-scrim"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    ></button>
    <aside class="sidebar" :class="{ 'is-open': mobileOpen }">
      <RouterLink v-if="!route.params.id" to="/home" class="brand"
        ><IconAperture :size="28" /><span>Higgsfield <small>STUDIO</small></span></RouterLink
      ><Button
        class="mobile-close icon-button"
        variant="ghost"
        aria-label="关闭导航"
        @click="mobileOpen = false"
        ><IconX :size="20"
      /></Button>
      <nav v-if="!route.params.id" aria-label="主导航">
        <RouterLink
          v-for="link in links"
          :key="link.path"
          :to="link.path"
          class="nav-link"
          @click="mobileOpen = false"
          ><component :is="link.icon" :size="20" /><span>{{ link.label }}</span></RouterLink
        >
      </nav>
      <div v-show="route.params.id" id="project-sidebar-navigation"></div>
      <div class="sidebar-projects" :class="{ 'in-project': route.params.id }">
        <span v-if="!route.params.id" class="section-label">项目空间</span
        ><RouterLink v-if="!route.params.id" to="/projects" class="nav-link" @click="mobileOpen = false"
          ><IconFolder :size="20" />我的项目<IconChevronRight class="push-right" :size="15"
        /></RouterLink>
        <p v-if="!route.params.id">仅显示你参与的项目</p>
        <div id="project-sidebar-tree"></div>
      </div>
      <div class="sidebar-bottom">
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
      </div>
    </aside>
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
  </div>
</template>
