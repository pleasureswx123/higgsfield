import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import useUserStore from '@/store/modules/user'
import { endPriceActivation } from '@/api/studio/prices'
import { priceEndPayload } from '@/utils/pricePublish'

export function usePriceActivationEnd(onSaved) {
  const user = useUserStore()
  const canWrite = computed(
    () => !!user.token && (user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:publish'))
  )
  const open = ref(false),
    pending = ref(false),
    uncertain = ref(false),
    error = ref(''),
    formRef = ref()
  const version = ref()
  const form = reactive({ effectiveUntil: '', reason: '' })
  let alive = true,
    signature = '',
    key = '',
    attempt, controller, epoch = 0, active = true
  function reset() {
    epoch++
    controller?.abort()
    attempt = undefined
    signature = ''; key = ''
    open.value = false; pending.value = false; uncertain.value = false
    error.value = ''; version.value = undefined
    for (const field of Object.keys(form)) form[field] = ''
  }
  function start(target) {
    if (!alive || !active || pending.value || uncertain.value || !canWrite.value) return
    if (!target?.id || !target?.revision) return
    version.value = JSON.parse(JSON.stringify(target))
    Object.assign(form, { effectiveUntil: '', reason: '' })
    error.value = ''
    signature = ''
    key = ''
    attempt = undefined
    uncertain.value = false
    open.value = true
  }
  function close() {
    if (!pending.value && !uncertain.value) {
      open.value = false
      error.value = ''
    }
  }
  async function submit() {
    if (!alive || !active || pending.value || !open.value || !canWrite.value) return
    const current = epoch
    pending.value = true
    error.value = ''
    try {
      if (!attempt) {
        if (!(await formRef.value?.validate().catch(() => false))) return
        if (!alive || !active || current !== epoch || !canWrite.value) return
        const payload = priceEndPayload(form, version.value)
        const next = JSON.stringify([version.value.id, payload])
        if (next !== signature) {
          signature = next
          key = crypto.randomUUID()
        }
        attempt = { id: version.value.id, payload, key }
      }
      uncertain.value = true
      controller = new AbortController()
      const response = await endPriceActivation(attempt.id, attempt.payload, attempt.key, controller.signal)
      if (alive && current === epoch && canWrite.value) {
        uncertain.value = false
        attempt = undefined
        open.value = false
        onSaved(response.data)
      }
    } catch (cause) {
      if (!alive || current !== epoch) return
      const code = cause?.response?.status ?? cause?.code
      if (cause?.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
          (code === 601 || (code >= 400 && code < 500))) {
        uncertain.value = false
        attempt = undefined
      }
      if (alive)
        error.value = cause instanceof Error ? cause.message : '结束区间未确认成功，请核对后重试'
    } finally {
      if (alive && current === epoch) pending.value = false
    }
  }
  watch(() => [user.token, user.id, JSON.stringify(user.permissions)], reset, { flush: 'sync' })
  onDeactivated(() => {
    active = false
    epoch++
    controller?.abort()
    pending.value = false
    uncertain.value = Boolean(attempt)
  })
  onActivated(() => { active = true })
  onBeforeRouteLeave(() => {
    if (pending.value || uncertain.value) return false
    if (!open.value || !Object.values(form).some(value => value !== '')) return true
    const current = epoch
    return ElMessageBox.confirm('价格操作尚未提交，离开后可能丢失当前输入。是否离开？', '未提交修改', {
      confirmButtonText: '离开', cancelButtonText: '继续编辑', type: 'warning',
    }).then(() => current === epoch && !pending.value && !uncertain.value).catch(() => false)
  })
  onBeforeUnmount(() => {
    alive = false
    reset()
  })
  return { canWrite, open, pending, uncertain, error, version, formRef, form, start, close, submit }
}
