import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/auth'
import { clearCommentRecovery } from '@/utils/commentRecovery'
import { clearGenerationRecovery } from '@/utils/generationRecovery'
export const useAuthStore = defineStore('studio-auth', () => {
  const token = ref('')
  const user = ref<api.UserInfo | null>(null)
  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  function clear() {
    clearGenerationRecovery()
    clearCommentRecovery()
    token.value = ''
    user.value = null
  }
  async function signIn(input: api.LoginInput) {
    const result = await api.login(input)
    if (!result.token) throw new Error('登录响应缺少凭据，请联系管理员')
    token.value = result.token
    try {
      user.value = await api.getUserInfo()
    } catch (error) {
      clear()
      throw error
    }
  }
  async function signOut() {
    try {
      await api.logout()
    } finally {
      clear()
    }
  }
  return { token, user, isAuthenticated, clear, signIn, signOut }
})
