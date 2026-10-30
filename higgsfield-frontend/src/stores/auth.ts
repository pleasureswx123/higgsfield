import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/auth'
import { clearCommentRecovery } from '@/utils/commentRecovery'
import { clearGenerationRecovery } from '@/utils/generationRecovery'

// 制作端独立、标签页级会话；不保存密码或用户权限快照。
const sessionKey = 'higgsfield.studio.session-token'
function readSession() {
  try { return sessionStorage.getItem(sessionKey) || '' } catch { return '' }
}
function saveSession(value: string) {
  try {
    if (value) sessionStorage.setItem(sessionKey, value)
    else sessionStorage.removeItem(sessionKey)
  } catch { /* 浏览器禁止存储时仍允许本次内存会话。 */ }
}
export const useAuthStore = defineStore('studio-auth', () => {
  const token = ref(readSession())
  const user = ref<api.UserInfo | null>(null)
  const restoreError = ref('')
  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  let epoch = 0
  let restoration: Promise<void> | undefined
  function clear() {
    epoch++
    clearGenerationRecovery()
    clearCommentRecovery()
    token.value = ''
    user.value = null
    restoreError.value = ''
    saveSession('')
  }
  async function restoreSession() {
    if (isAuthenticated.value || !token.value) return
    if (restoration) return restoration
    const stamp = epoch, credential = token.value
    restoreError.value = ''
    const pending = (async () => {
      try {
        const result = await api.getUserInfo()
        if (epoch === stamp && token.value === credential) user.value = result
      } catch (cause) {
        if (epoch !== stamp || token.value !== credential) return
        if ((cause as { code?: number })?.code === 401) clear()
        else restoreError.value = '暂时无法恢复登录状态，请检查网络或服务后重试，无需重新输入密码。'
      }
    })()
    restoration = pending
    try { await pending } finally { if (restoration === pending) restoration = undefined }
  }
  async function signIn(input: api.LoginInput) {
    clear()
    const stamp = epoch
    const result = await api.login(input)
    if (stamp !== epoch) throw new Error('登录操作已取消')
    if (!result.token) throw new Error('登录响应缺少凭据，请联系管理员')
    token.value = result.token
    try {
      const info = await api.getUserInfo()
      if (stamp !== epoch) throw new Error('登录状态已变化，请重试')
      user.value = info
      saveSession(token.value)
    } catch (error) {
      if (stamp === epoch) clear()
      throw error
    }
  }
  async function signOut() {
    // 先使旧恢复请求失效，保留令牌直到退出请求发送完成。
    const stamp = ++epoch
    saveSession('')
    try { await api.logout() } finally { if (stamp === epoch) clear() }
  }
  return { token, user, isAuthenticated, restoreError, restoreSession, clear, signIn, signOut }
})
