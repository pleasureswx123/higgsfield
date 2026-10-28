import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import { listBillingEvents, getBillingEvent, getBillingSummary } from '@/api/studio/billing'
import { billingTimeWindow } from '@/utils/billingQuery'

export function useBillingEvents() {
  const user = useUserStore()
  const allowed = computed(() => !!user.token && (user.permissions.includes('*:*:*') || user.permissions.includes('billing:read')))
  const filters = reactive({
    purpose: 'platform',
    scope: 'project',
    costCenterId: '',
    currency: '',
    state: '',
    projectId: '',
    jobId: '',
    userId: '',
    timeRange: [],
    mode: 'events',
    groupBy: 'project',
    costCenterGroupBy: 'cost_center',
  })
  const formRef = ref(),
    rows = ref([]),
    summary = ref(),
    total = ref(0),
    page = ref(1)
  const loading = ref(false),
    error = ref(''),
    detail = ref(),
    detailOpen = ref(false)
  const detailLoading = ref(false),
    detailError = ref('')
  let listController,
    detailController,
    active = false
  function closeDetail() {
    detailController?.abort()
    detailController = undefined
    detailOpen.value = false
    detail.value = undefined
    detailLoading.value = false
    detailError.value = ''
  }
  function clear() {
    listController?.abort()
    listController = undefined
    rows.value = []
    summary.value = undefined
    total.value = 0
    loading.value = false
    error.value = ''
    closeDetail()
  }
  async function load() {
    clear()
    if (!active || !allowed.value) return
    const controller = new AbortController()
    listController = controller
    loading.value = true
    try {
      const params = {
        pageNum: page.value,
        pageSize: 20,
        purpose: filters.purpose,
        ...billingTimeWindow(filters.timeRange),
      }
      for (const field of ['currency', 'projectId', 'userId'])
        if (filters[field]) params[field] = filters[field]
      params.scope = filters.scope
      if (filters.scope === 'cost_center') {
        delete params.projectId; delete params.userId
        if (filters.costCenterId) params.costCenterId = filters.costCenterId
      }
      if (filters.mode === 'summary') {
        if (!params.from || !params.to) throw new Error('汇总查询必须选择起止时间')
        delete params.pageNum
        delete params.pageSize
        Object.assign(params, {
          groupBy: filters.scope === 'cost_center' ? filters.costCenterGroupBy : filters.groupBy,
          timeBasis: 'createTime',
          businessTimezone: 'Asia/Shanghai',
        })
        const result = await getBillingSummary(params, controller.signal)
        if (!controller.signal.aborted) summary.value = result.data
        return
      }
      for (const field of ['state', 'jobId']) if (filters[field]) params[field] = filters[field]
      if (filters.scope === 'cost_center') {
        delete params.projectId; delete params.jobId; delete params.userId
      }
      const result = await listBillingEvents(params, controller.signal)
      if (!controller.signal.aborted) {
        rows.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '费用读取失败'
    } finally {
      if (listController === controller) loading.value = false
    }
  }
  async function search() {
    clear()
    if (!(await formRef.value?.validate().catch(() => false))) return
    page.value = 1
    await load()
  }
  async function select(row) {
    closeDetail()
    if (!active || !allowed.value) return
    const controller = new AbortController()
    detailController = controller
    detailOpen.value = true
    detailLoading.value = true
    try {
      const result = await getBillingEvent(row.id, controller.signal)
      if (!controller.signal.aborted) detail.value = result.data
    } catch (cause) {
      if (!controller.signal.aborted)
        detailError.value = cause instanceof Error ? cause.message : '费用明细读取失败'
    } finally {
      if (detailController === controller) detailLoading.value = false
    }
  }
  function activate() {
    if (!active) {
      active = true
      void load()
    }
  }
  function deactivate() {
    active = false
    clear()
  }
  watch(filters, clear, { flush: 'sync' })
  watch(() => [user.token, user.id, JSON.stringify(user.permissions)], () => {
    clear()
    if (active && allowed.value) void load()
  }, { flush: 'sync' })
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return {
    allowed,
    filters,
    formRef,
    rows,
    summary,
    total,
    page,
    loading,
    error,
    detail,
    detailOpen,
    detailLoading,
    detailError,
    search,
    load,
    select,
    closeDetail,
  }
}
