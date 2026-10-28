import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import { onBeforeRouteLeave } from 'vue-router'
import { adjustBillingEvent } from '@/api/studio/billing'

export function useBillingAdjustment(event, onSaved) {
  const user = useUserStore()
  const canAdjust = computed(
    () => !!user.token && (user.permissions.includes('*:*:*') || user.permissions.includes('billing:adjust'))
  )
  const form = reactive({ deltaAmount: '', reason: '', reconciliationLineId: '' }),
    formRef = ref()
  const pending = ref(false),
    error = ref(''), uncertain = ref(false)
  let alive = true, active = true, epoch = 0, attempt, controller
  function reset() {
    epoch++
    controller?.abort()
    attempt = undefined
    pending.value = false; uncertain.value = false; error.value = ''
    Object.assign(form, { deltaAmount: '', reason: '', reconciliationLineId: '' })
  }
  async function submit() {
    if (pending.value || !alive || !active || !canAdjust.value || (!attempt && event()?.amount == null)) return
    pending.value = true
    error.value = ''
    const original = event(), current = epoch
    try {
      if (!attempt) {
        if (!(await formRef.value?.validate().catch(() => false))) return
        if (!alive || !active || current !== epoch || !canAdjust.value || original !== event()) return
        const payload = {
          revision: original.revision,
          deltaAmount: form.deltaAmount,
          reason: form.reason.trim(),
          ...(form.reconciliationLineId.trim() ? { reconciliationLineId: form.reconciliationLineId.trim() } : {}),
        }
        attempt = { id: original.id, payload, key: crypto.randomUUID() }
      }
      uncertain.value = true
      controller = new AbortController()
      await adjustBillingEvent(attempt.id, attempt.payload, attempt.key, controller.signal)
      if (alive && current === epoch) { reset(); onSaved() }
    } catch (cause) {
      if (!alive || current !== epoch) return
      const code = cause?.response?.status ?? cause?.code
      if (cause?.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' && (code === 601 || (code >= 400 && code < 500))) {
        attempt = undefined
        uncertain.value = false
      }
      if (alive)
        error.value = cause instanceof Error ? cause.message : '调整未确认成功，请核对后重试'
    } finally {
      if (alive && current === epoch) pending.value = false
    }
  }
  watch(() => [event()?.id, user.token, user.id, JSON.stringify(user.permissions)], reset, { flush: 'sync' })
  onDeactivated(() => {
    active = false; epoch++; controller?.abort()
    pending.value = false; uncertain.value = Boolean(attempt)
  })
  onActivated(() => { active = true })
  onBeforeUnmount(() => {
    alive = false
    reset()
  })
  onBeforeRouteLeave(() => !pending.value && !uncertain.value)
  return { canAdjust, form, formRef, pending, uncertain, error, submit }
}
