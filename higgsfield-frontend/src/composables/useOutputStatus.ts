import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { updateOutputStatus, type GenerationOutput } from '@/api/generations'

export function useOutputStatus(output: () => GenerationOutput | undefined, saved: () => void, close: () => void) {
  const auth = useAuthStore()
  const status = ref<GenerationOutput['workStatus']>('none'), reason = ref('')
  const pending = ref(false), retryable = ref(false), error = ref('')
  const allowed = computed(() => !!output()?.allowedActions.includes('output:work-status'))
  let epoch = 0, request: AbortController | undefined
  let baseRevision = ''
  let attempt: { id: string; key: string; data: { revision: string; workStatus: GenerationOutput['workStatus']; reason: string } } | undefined
  function reset() {
    epoch++
    request?.abort()
    attempt = undefined
    pending.value = false
    retryable.value = false
    error.value = ''
    status.value = output()?.workStatus ?? 'none'
    baseRevision = output()?.revision ?? ''
    reason.value = ''
  }
  async function submit(validate?: () => Promise<boolean>) {
    if (!attempt && validate) {
      const ticket = epoch, before = JSON.stringify([status.value, reason.value, baseRevision])
      if (!(await validate()) || ticket !== epoch || before !== JSON.stringify([status.value, reason.value, baseRevision])) return
    }
    const row = output()
    if (pending.value || !auth.token || !row || (!attempt && !allowed.value)) return
    if (!attempt) attempt = { id: row.id, key: crypto.randomUUID(),
      data: { revision: baseRevision, workStatus: status.value, reason: reason.value.trim() } }
    const ticket = epoch
    request = new AbortController()
    pending.value = true
    error.value = ''
    try {
      await updateOutputStatus(attempt.id, attempt.data, attempt.key, request.signal)
      if (ticket !== epoch) return
      attempt = undefined
      retryable.value = false
      saved()
      close()
    } catch (cause) {
      if (ticket !== epoch) return
      const { code, errorCode } = (cause ?? {}) as { code?: number; errorCode?: string }
      retryable.value = errorCode === 'IDEMPOTENCY_IN_PROGRESS' || code === undefined || code === 0 || (code >= 500 && code !== 601)
      if (!retryable.value) { attempt = undefined; saved() }
      error.value = cause instanceof Error ? cause.message : '状态保存失败，请核对后重试'
    } finally {
      if (ticket === epoch) pending.value = false
    }
  }
  watch(() => output()?.id, () => { reset(); if (!output()) close() }, { immediate: true, flush: 'sync' })
  watch(() => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions ?? [])], () => { reset(); close() }, { flush: 'sync' })
  onBeforeUnmount(reset)
  function reload() { if (!pending.value && !retryable.value) reset() }
  return { status, reason, pending, retryable, error, allowed, submit, reload }
}
