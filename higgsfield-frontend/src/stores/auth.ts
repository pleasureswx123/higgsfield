import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/auth'
import { clearCommentRecovery } from '@/utils/commentRecovery'
import { clearGenerationRecovery } from '@/utils/generationRecovery'

import { readDeviceSession, removeDeviceSession, writeDeviceSession } from '@/utils/rememberedLogin'

// 普通登录保存在标签页；主动记住的设备会话单独加密保存。
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
  let deviceId = ''
  let deadline = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  function trackDevice(id: string, expires: number) {
    deviceId = id
    deadline = expires
    clearTimeout(timer)
    timer = setTimeout(clear, Math.max(0, expires - Date.now()))
  }
  async function rememberSession(expires: number) {
    const stamp = epoch
    if (!isAuthenticated.value) return
    const id = await writeDeviceSession(token.value, expires)
    if (stamp !== epoch) { removeDeviceSession(id); return }
    trackDevice(id, expires)
    saveSession('')
  }
  function discardDevice() {
    clearTimeout(timer)
    if (deviceId) {
      try { removeDeviceSession(deviceId) } catch { /* 存储受限时仍要退出当前会话。 */ }
    }
    deviceId = ''
    deadline = 0
  }
  function clear() {
    discardDevice()
    epoch++
    clearGenerationRecovery()
    clearCommentRecovery()
    token.value = ''
    user.value = null
    restoreError.value = ''
    saveSession('')
  }
  async function restoreSession() {
    if (deadline && deadline <= Date.now()) clear()
    if (isAuthenticated.value) return
    if (restoration) return restoration
    const stamp = epoch
    restoreError.value = ''
    const pending = (async () => {
      if (!token.value) {
        const saved = await readDeviceSession().catch(() => undefined)
        if (!saved || epoch !== stamp) return
        trackDevice(saved.id, saved.expires)
        token.value = saved.token
      }
      const credential = token.value
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
    discardDevice()
    saveSession('')
    try { await api.logout() } finally { if (stamp === epoch) clear() }
  }
  return { token, user, isAuthenticated, restoreError, restoreSession, clear, signIn, signOut, rememberSession, usesDeviceSession: () => Boolean(deviceId) }
})
