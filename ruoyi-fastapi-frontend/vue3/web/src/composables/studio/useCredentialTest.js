import { computed, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { listCredentialTestModels, listTestCostCenters, createCredentialTest } from '@/api/studio/credentials'

export function useCredentialTest() {
  const user = useUserStore()
  const allowed = computed(() => user.permissions.includes('*:*:*') || user.permissions.includes('credential:test'))
  const open = ref(false), pending = ref(false), error = ref(''), target = ref(null), receipt = ref(null), formRef = ref()
  const form = reactive({ modelVersionId: '', costCenterId: '', acknowledgePotentialCharge: false })
  const section = () => reactive({ rows: [], page: 1, total: 0, loading: false, error: '' })
  const models = section(), centers = section(), controllers = new Map()
  let epoch = 0, signature = '', key = ''
  function reset() {
    epoch++
    for (const controller of controllers.values()) controller.abort()
    controllers.clear()
    for (const part of [models, centers]) Object.assign(part, { rows: [], page: 1, total: 0, loading: false, error: '' })
    open.value = false
    target.value = receipt.value = null
    error.value = ''
    Object.assign(form, { modelVersionId: '', costCenterId: '', acknowledgePotentialCharge: false })
    signature = key = ''
  }
  async function load(part) {
    if (!open.value || pending.value || !allowed.value || receipt.value) return
    controllers.get(part)?.abort()
    const controller = new AbortController(), token = epoch
    controllers.set(part, controller)
    part.loading = true
    part.error = ''
    part.rows = []
    if (part === models) form.modelVersionId = ''
    else form.costCenterId = ''
    try {
      const query = { pageNum: part.page, pageSize: 20 }
      const response = part === models
        ? await listCredentialTestModels(target.value.id, query, controller.signal)
        : await listTestCostCenters(query, controller.signal)
      if (token !== epoch || controllers.get(part) !== controller || !allowed.value) return
      part.rows = response.rows || []
      part.total = response.total || 0
    } catch (cause) {
      if (token === epoch && controllers.get(part) === controller) {
        part.total = 0
        part.error = cause instanceof Error ? cause.message : '读取选项失败'
      }
    } finally { if (token === epoch && controllers.get(part) === controller) part.loading = false }
  }
  function start(row) {
    if (pending.value || !allowed.value || !['draft', 'active'].includes(row.state)) return
    reset()
    target.value = { ...row }
    open.value = true
    load(models)
    load(centers)
  }
  function close() { if (!pending.value) reset() }
  async function submit() {
    if (pending.value || receipt.value || !open.value || !allowed.value || models.loading || centers.loading) return
    pending.value = true
    const token = epoch
    try {
      if (!(await formRef.value?.validate().catch(() => false)) || token !== epoch || !allowed.value) return
      if (form.acknowledgePotentialCharge !== true || !models.rows.some(row => row.id === form.modelVersionId)
          || !centers.rows.some(row => row.id === form.costCenterId && row.active)) {
        error.value = '请选择有效模型和成本中心，并确认潜在费用'
        return
      }
      const data = { ...form }, next = JSON.stringify([target.value.id, data])
      if (next !== signature) { signature = next; key = crypto.randomUUID() }
      error.value = ''
      const response = await createCredentialTest(target.value.id, data, key)
      if (token === epoch && allowed.value) receipt.value = response.data
    } catch (cause) {
      if (token === epoch) error.value = cause instanceof Error ? cause.message : '测试申请失败'
    } finally { pending.value = false }
  }
  watch(allowed, value => { if (!value) reset() }, { flush: 'sync' })
  onBeforeRouteLeave(() => {
    if (pending.value) return false
    if (open.value && !receipt.value && (form.modelVersionId || form.costCenterId)
        && !window.confirm('离开将丢弃未提交的测试申请，是否继续？')) return false
    reset()
    return true
  })
  const beforeUnload = event => {
    if (pending.value || (open.value && !receipt.value && (form.modelVersionId || form.costCenterId))) {
      event.preventDefault(); event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onDeactivated(reset)
  onBeforeUnmount(() => { reset(); window.removeEventListener('beforeunload', beforeUnload) })
  return { allowed, open, pending, error, target, receipt, formRef, form, models, centers, start, close, load, submit }
}
