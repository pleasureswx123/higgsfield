import { computed, reactive, ref, watch, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import { releaseTestCapacity } from '@/api/studio/credentials'

/** 只处理已结束未知测试的名额，不发起模型生成。 */
export function useTestCapacityRelease(testId, refresh) {
  const user = useUserStore()
  const allowed = computed(() => !!user.token && (user.permissions.includes('*:*:*') || user.permissions.includes('credential:test')))
  const form = reactive({ reason: '', evidenceRef: '', acknowledgeSupplierStopped: false })
  const pending = ref(false), uncertain = ref(false), error = ref('')
  let epoch = 0, attempt
  function reset() {
    epoch++; attempt = undefined; pending.value = uncertain.value = false; error.value = ''
    Object.assign(form, { reason: '', evidenceRef: '', acknowledgeSupplierStopped: false })
  }
  async function submit() {
    if (!allowed.value || pending.value || !testId()) return
    const ticket = epoch
    if (!attempt) {
      if (!form.reason.trim() || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$/.test(form.evidenceRef.trim()) || !form.acknowledgeSupplierStopped) {
        error.value = '请填写核查原因、证据引用，并确认供应商任务已停止或未运行'; return
      }
      attempt = { id: testId(), key: crypto.randomUUID(), data: { reason: form.reason.trim(), evidenceRef: form.evidenceRef.trim(), acknowledgeSupplierStopped: true } }
    }
    pending.value = true; error.value = ''; uncertain.value = true
    try {
      await releaseTestCapacity(attempt.id, attempt.data, attempt.key)
      if (ticket === epoch && allowed.value) { reset(); await refresh() }
    } catch (cause) {
      if (ticket === epoch) {
        const code = cause?.response?.status ?? cause?.code
        if (cause?.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' && (code === 601 || (code >= 400 && code < 500 && code !== 408))) {
          attempt = undefined; uncertain.value = false
        }
        error.value = cause?.message || '释放结果尚未确认，请重试确认原请求'
      }
    } finally { if (ticket === epoch) pending.value = false }
  }
  watch(() => [testId(), user.token, user.id, JSON.stringify(user.permissions)], reset, { flush: 'sync' })
  onBeforeUnmount(reset)
  return { allowed, form, pending, uncertain, error, submit }
}
