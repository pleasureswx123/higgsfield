import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { cancelGeneration, type GenerationSnapshot } from '@/api/generations'

export function useGenerationCancel(
  identity: () => string | undefined,
  snapshot: () => GenerationSnapshot | undefined,
  refresh: () => Promise<void>,
) {
  const auth = useAuthStore()
  let active = true
  let request: AbortController | undefined
  const reason = ref('用户取消尚未提交的任务')
  const pending = ref(false),
    error = ref(''),
    retryable = ref(false)
  let version = 0
  let attempt: { id: string; key: string; data: { revision: string; reason: string } } | undefined
  function reset() {
    request?.abort()
    version++
    attempt = undefined
    pending.value = false
    retryable.value = false
    error.value = ''
    reason.value = '用户取消尚未提交的任务'
  }
  async function submit() {
    if (pending.value || !active || !auth.token) return
    const id = identity(),
      task = snapshot()
    if (!id || !task || task.id !== id) return
    if (!attempt) {
      if (!task.allowedActions.includes('generation:cancel') || !reason.value.trim()) return
      attempt = {
        id,
        key: crypto.randomUUID(),
        data: { revision: task.revision, reason: reason.value.trim() },
      }
    }
    const current = version
    request = new AbortController()
    pending.value = true
    error.value = ''
    let acknowledged = false
    try {
      await cancelGeneration(attempt.id, attempt.data, attempt.key, request.signal)
      if (version !== current) return
      acknowledged = true
      attempt = undefined
      retryable.value = false
      await refresh()
    } catch (cause) {
      if (version !== current) return
      // 未收到明确业务响应时保留原请求，防止重复取消或改变重试语义。
      const { code, errorCode } = cause as { code?: number; errorCode?: string }
      retryable.value = !acknowledged && (
        errorCode === 'IDEMPOTENCY_IN_PROGRESS' ||
        code === undefined || code === 0 || (code >= 500 && code !== 601)
      )
      if (!retryable.value && !acknowledged) {
        attempt = undefined
        await refresh()
      }
      if (version === current)
        error.value = cause instanceof Error ? cause.message : '取消失败，请重试'
    } finally {
      if (version === current) pending.value = false
    }
  }
  watch(() => [identity(), auth.token, JSON.stringify(auth.user?.permissions || [])], reset, { flush: 'sync' })
  onDeactivated(() => {
    active = false
    version++
    request?.abort()
    pending.value = false
    retryable.value = Boolean(attempt)
  })
  onActivated(() => { active = true })
  onBeforeUnmount(() => { active = false; reset() })
  return { reason, pending, error, retryable, submit }
}
