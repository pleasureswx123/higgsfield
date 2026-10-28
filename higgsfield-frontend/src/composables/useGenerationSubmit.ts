import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { readGenerationRecovery, saveGenerationRecovery, finishGenerationRecovery } from '@/utils/generationRecovery'
import {
  submitGeneration,
  validateGeneration,
  type GenerationSubmission,
  type GenerationValidation,
} from '@/api/generations'

export function useGenerationSubmit(input: () => GenerationSubmission | undefined, projectId: () => string = () => input()?.projectId || '') {
  const auth = useAuthStore()
  let active = true,
    epoch = 0
  const currentSession = (ticket: number) => alive && ticket === epoch && Boolean(auth.token)
  const checking = ref(false),
    submitting = ref(false),
    uncertain = ref(false)
  const generating = ref(false)
  const error = ref(''),
    acceptedId = ref<string>()
  const quote = ref<GenerationValidation>()
  const visibleEstimate = computed(() =>
    quote.value?.estimateVisibility === 'visible' ? quote.value.estimate : undefined,
  )
  const locked = computed(() => submitting.value || uncertain.value)
  const signature = computed(() => JSON.stringify(input()))
  let quoteSignature = '',
    controller: AbortController | undefined,
    alive = true
  let attempt: { data: GenerationSubmission; key: string } | undefined
  function restoreAttempt() {
    const saved = readGenerationRecovery(auth.token, projectId())
    if (saved && (!attempt || saved.key !== attempt.key)) {
      attempt = saved
      uncertain.value = true
      invalidate()
      error.value = '该项目有尚未确认的生成请求，请先确认原请求结果。'
    }
  }
  function invalidate() {
    controller?.abort()
    checking.value = false
    quote.value = undefined
    quoteSignature = ''
  }
  watch(signature, invalidate, { flush: 'sync' })
  async function check() {
    restoreAttempt()
    if (!alive || !active || !auth.token || locked.value) return
    invalidate()
    error.value = ''
    acceptedId.value = undefined
    const payload = input()
    if (!payload) {
      error.value = '请先选择可用模型'
      return
    }
    const current = new AbortController()
    controller = current
    const savedSignature = signature.value
    const ticket = epoch
    checking.value = true
    try {
      const result = await validateGeneration(JSON.parse(JSON.stringify(payload)), current.signal)
      if (!currentSession(ticket) || current.signal.aborted || savedSignature !== signature.value)
        return
      quote.value = result.data
      quoteSignature = savedSignature
      return result.data.valid
    } catch (cause) {
      if (currentSession(ticket) && !current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '预检失败'
    } finally {
      if (currentSession(ticket) && !current.signal.aborted) checking.value = false
    }
  }
  async function submit() {
    if (submitting.value || !alive || !active || !auth.token) return
    restoreAttempt()
    const ticket = epoch
    const token = auth.token, project = projectId()
    if (!attempt) {
      const payload = input(),
        value = quote.value
      if (!payload || !value?.valid || !value.estimateToken || signature.value !== quoteSignature)
        return
      if (
        !value.expiresAt ||
        Date.parse(value.expiresAt) <= Date.now() ||
        !Number.isFinite(Date.parse(value.expiresAt))
      ) {
        invalidate()
        error.value = '估价已过期，请重新预检'
        return
      }
      attempt = {
        data: JSON.parse(JSON.stringify({ ...payload, estimateToken: value.estimateToken })),
        key: crypto.randomUUID(),
      }
      saveGenerationRecovery(token, project, attempt)
    }
    const sent = attempt
    submitting.value = true
    error.value = ''
    try {
      const result = await submitGeneration(sent.data, sent.key)
      finishGenerationRecovery(token, project, sent.key)
      if (!currentSession(ticket)) return
      acceptedId.value = result.data.id
      attempt = undefined
      uncertain.value = false
      invalidate()
    } catch (cause) {
      if (!currentSession(ticket)) return
      const code = (cause as { code?: number }).code
      uncertain.value =
        code === undefined ||
        code === 0 ||
        code === 408 ||
        (code >= 500 && code !== 601) ||
        (cause as { errorCode?: string }).errorCode === 'IDEMPOTENCY_IN_PROGRESS'
      if (!uncertain.value) {
        finishGenerationRecovery(token, project, sent.key)
        attempt = undefined
        invalidate()
      }
      error.value = cause instanceof Error ? cause.message : '提交失败，请重试'
    } finally {
      if (currentSession(ticket)) submitting.value = false
    }
  }
  async function generate() {
    if (generating.value || checking.value || locked.value) return
    generating.value = true
    try {
      // 只提交本次检查通过的输入；提交仍校验签名、有效期及会话。
      if (await check()) await submit()
    } finally {
      generating.value = false
    }
  }
  onBeforeRouteLeave(() => !locked.value)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || !locked.value)
  watch(
    () => auth.token,
    () => {
      epoch++
      invalidate()
      attempt = undefined
      submitting.value = false
      uncertain.value = false
      acceptedId.value = undefined
      error.value = ''
      restoreAttempt()
    },
    { flush: 'sync' },
  )
  watch(() => JSON.stringify(auth.user?.permissions || []), invalidate, { flush: 'sync' })
  onDeactivated(() => {
    active = false
    invalidate()
  })
  onActivated(() => {
    active = true
  })
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (locked.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  window.addEventListener('beforeunload', beforeUnload)
  restoreAttempt()
  onBeforeUnmount(() => {
    alive = false
    invalidate()
    window.removeEventListener('beforeunload', beforeUnload)
  })
  return { generate, generating, checking, submitting, uncertain, locked, quote, visibleEstimate, error, acceptedId, check, submit }
}
