import { computed, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { getCredentialTest, listCredentialTests, changeCredentialState } from '@/api/studio/credentials'

export function useCredentialActivation(refresh) {
  const user = useUserStore()
  const allowed = computed(() => user.permissions.includes('credential:read') || user.permissions.includes('*:*:*'))
  const canActivate = computed(() => allowed.value && (user.permissions.includes('credential:activate') || user.permissions.includes('*:*:*')))
  const canReadCost = computed(() => user.permissions.includes('billing:read') || user.permissions.includes('*:*:*'))
  function protectCost(record) {
    if (!record || canReadCost.value) return record
    const { cost, ...visible } = record
    return { ...visible, costVisibility: 'hidden' }
  }
  const open = ref(false), pending = ref(false), loading = ref(false), error = ref('')
  const target = ref(null), result = ref(null), formRef = ref()
  const form = reactive({ testId: '', reason: '' })
  const history = reactive({ rows: [], page: 1, total: 0, loading: false, error: '' })
  let historyController, historyEpoch = 0
  let controller, epoch = 0, signature = '', key = ''
  const eligible = computed(() => canActivate.value && target.value?.state === 'draft'
    && result.value?.state === 'passed' && result.value?.result?.modelVerified === true
    && result.value?.credentialVersionId === target.value?.id
    && result.value?.id === form.testId.trim() && /^[a-f0-9]{64}$/.test(result.value?.configHash || ''))
  function invalidate() {
    epoch++
    controller?.abort()
    result.value = null
    loading.value = false
  }
  function reset() {
    historyEpoch++
    historyController?.abort()
    Object.assign(history, { rows: [], page: 1, total: 0, loading: false, error: '' })
    invalidate()
    open.value = false
    target.value = null
    form.testId = ''
    form.reason = ''
    error.value = ''
    signature = key = ''
  }
  function start(row) {
    if (pending.value || !allowed.value) return
    reset()
    target.value = { ...row }
    open.value = true
    loadHistory()
  }
  async function loadHistory() {
    if (!open.value || pending.value || !allowed.value) return
    historyController?.abort()
    historyController = new AbortController()
    const token = ++historyEpoch
    history.loading = true
    history.error = ''
    history.rows = []
    try {
      const response = await listCredentialTests(target.value.id, { pageNum: history.page, pageSize: 10 }, historyController.signal)
      if (token !== historyEpoch || !allowed.value) return
      history.rows = (response.rows || []).map(protectCost)
      history.total = response.total || 0
    } catch (cause) {
      if (token === historyEpoch) { history.total = 0; history.error = cause instanceof Error ? cause.message : '读取测试历史失败' }
    } finally { if (token === historyEpoch) history.loading = false }
  }
  function chooseTest(row) {
    if (pending.value || !open.value || !allowed.value) return
    form.testId = row.id
    inspect()
  }
  function close() { if (!pending.value) reset() }
  async function inspect() {
    if (!open.value || pending.value || !allowed.value) return
    invalidate()
    const id = form.testId.trim(), token = epoch
    if (!/^[1-9]\d{0,18}$/.test(id)) { error.value = '请输入有效测试记录编号'; return }
    controller = new AbortController()
    loading.value = true
    error.value = ''
    try {
      const response = await getCredentialTest(id, controller.signal)
      if (token !== epoch || !allowed.value) return
      result.value = protectCost(response.data)
      if (result.value?.credentialVersionId !== target.value?.id) {
        result.value = null
        error.value = '该测试不属于当前凭据版本'
      }
    } catch (cause) {
      if (token === epoch) error.value = cause instanceof Error ? cause.message : '读取测试失败'
    } finally { if (token === epoch) loading.value = false }
  }
  async function submit() {
    if (pending.value || !eligible.value) return
    pending.value = true
    const token = epoch
    try {
      if (!(await formRef.value?.validate().catch(() => false)) || token !== epoch || !eligible.value) return
      const data = { revision: target.value.revision, testId: result.value.id,
        expectedConfigHash: result.value.configHash, reason: form.reason.trim() }
      const next = JSON.stringify([target.value.id, data])
      if (next !== signature) { signature = next; key = crypto.randomUUID() }
      error.value = ''
      await changeCredentialState(target.value.id, 'activate', data, key)
      if (token !== epoch || !allowed.value) return
      reset()
      await refresh()
    } catch (cause) {
      if (token === epoch) error.value = cause instanceof Error ? cause.message : '启用失败，请刷新凭据与测试后重试'
    } finally { pending.value = false }
  }
  watch(() => form.testId, invalidate, { flush: 'sync' })
  watch(allowed, value => { if (!value) reset() }, { flush: 'sync' })
  watch(canReadCost, value => {
    if (!value) {
      result.value = protectCost(result.value)
      history.rows = history.rows.map(protectCost)
    }
  }, { flush: 'sync' })
  onBeforeRouteLeave(() => {
    if (pending.value) return false
    if (open.value && (form.reason || form.testId) && !window.confirm('离开将丢弃未提交的启用操作，是否继续？')) return false
    reset()
    return true
  })
  onDeactivated(reset)
  const beforeUnload = event => {
    if (pending.value || (open.value && (form.testId || form.reason))) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => { reset(); window.removeEventListener('beforeunload', beforeUnload) })
  return { allowed, canActivate, eligible, open, pending, loading, error, target, result, formRef, form, history,
    start, close, inspect, submit, loadHistory, chooseTest }
}
