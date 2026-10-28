import { computed, reactive, ref, watch, onDeactivated, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { recoverIncident } from '@/api/studio/incidents'

export function useIncidentRecovery(onSaved) {
  const user = useUserStore()
  const allowed = computed(() => !!user.token && (user.permissions.includes('*:*:*') ||
    (user.permissions.includes('operations:read') && user.permissions.includes('operations:recover'))))
  const target = ref(), pending = ref(false), uncertain = ref(false), error = ref(''), formRef = ref()
  const form = reactive({ reason: '', evidenceRef: '' })
  let epoch = 0, attempt, controller
  function reset() {
    controller?.abort()
    epoch++
    target.value = undefined
    pending.value = false
    uncertain.value = false
    error.value = ''
    form.reason = ''; form.evidenceRef = ''; attempt = undefined
  }
  function start(detail, action = 'retry_archive') {
    if (!['retry_archive', 'requery', 'close_tracking', 'confirm_not_accepted'].includes(action) || pending.value || uncertain.value || !allowed.value || !detail?.allowedActions?.includes(action)) return
    reset()
    target.value = { jobId: detail.jobId, revision: detail.revision, action }
  }
  function close() { if (!pending.value && !uncertain.value) reset() }
  async function submit() {
    if (!target.value || !allowed.value || pending.value) return
    const current = epoch
    pending.value = true
    error.value = ''
    try {
      if (!attempt) {
        if (!(await formRef.value?.validate().catch(() => false))) return
        if (current !== epoch || !allowed.value) return
        const data = { revision: target.value.revision, action: target.value.action, reason: form.reason.trim() }
        if (!data.reason || data.reason.length > 4000) throw new Error('请填写原因，最多4000字符')
        if (['close_tracking', 'confirm_not_accepted'].includes(data.action) && !form.evidenceRef.trim()) throw new Error('此操作必须填写证据引用')
        if (data.action === 'confirm_not_accepted' && !/^provider-call:[1-9][0-9]{0,18}$/.test(form.evidenceRef.trim())) throw new Error('请填写 provider-call 调用证据引用')
        if (form.evidenceRef.trim()) {
          if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$/.test(form.evidenceRef.trim())) throw new Error('证据引用只能包含字母、数字、点、冒号、下划线和短横线')
          data.evidenceRef = form.evidenceRef.trim()
        }
        attempt = { jobId: target.value.jobId, data, key: crypto.randomUUID() }
      }
      uncertain.value = true
      controller = new AbortController()
      await recoverIncident(attempt.jobId, attempt.data, attempt.key, controller.signal)
      if (current === epoch && allowed.value) { reset(); await onSaved() }
    } catch (cause) {
      if (current === epoch) {
        const code = cause?.response?.status ?? cause?.code
        if (cause?.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
            (code === 601 || (code >= 400 && code < 500))) {
          attempt = undefined
          uncertain.value = false
        }
        error.value = cause?.message || '恢复调度结果未确认，请保留当前内容重试'
      }
    } finally {
      if (current === epoch) pending.value = false
    }
  }
  watch(() => [user.token, user.id, JSON.stringify(user.permissions)], reset, { flush: 'sync' })
  onDeactivated(() => {
    if (!attempt) reset()
    else { epoch++; controller?.abort(); pending.value = false; uncertain.value = true }
  })
  onBeforeUnmount(reset)
  onBeforeRouteLeave(() => !pending.value && !uncertain.value)
  return { allowed, target, pending, uncertain, error, form, formRef, start, close, submit }
}
