<script setup lang="ts">
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useThemeStore } from '@/stores/theme'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Button from '@/components/ui/Button.vue'
useThemeStore()
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const retrying = ref(false)
async function retry() {
  if (retrying.value) return
  retrying.value = true
  try {
    await auth.restoreSession()
    if (auth.isAuthenticated && route.path === '/login') await router.replace('/home')
  } finally { retrying.value = false }
}
</script>
<template>
  <ElConfigProvider :locale="zhCn" :z-index="2000"><main v-if="auth.token && !auth.isAuthenticated && (auth.restoreError || retrying)" class="session-recovery">
    <p role="status">{{ retrying ? '正在恢复登录…' : auth.restoreError }}</p>
    <Button :disabled="retrying" @click="retry">重新连接</Button>
  </main><RouterView v-else /></ElConfigProvider>
</template>

<style scoped>
.session-recovery { min-height:100dvh; display:grid; align-content:center; justify-items:center; gap:12px; padding:24px; }
</style>
