import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import { listBillingEvents, listBillingConsumers, getBillingEvent, getBillingSubject, getBillingSummary } from '@/api/studio/billing'
import { billingTimeWindow } from '@/utils/billingQuery'

export function useBillingEvents() {
  const user = useUserStore()
  const allowed = computed(() => !!user.token && (user.permissions.includes('*:*:*') || user.permissions.includes('billing:read')))
  const defaultFilters = () => ({
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
  const filters = reactive(defaultFilters())
  const formRef = ref(),
    rows = ref([]),
    summary = ref(),
    total = ref(0),
    page = ref(1)
  const consumers = ref([]), consumersLoading = ref(false), consumersError = ref('')
  let consumersController
  async function searchConsumers(keyword = '') {
    consumersController?.abort()
    if (!active || !allowed.value) return
    const controller = new AbortController()
    consumersController = controller
    consumersLoading.value = true
    consumersError.value = ''
    try {
      const result = await listBillingConsumers(keyword, controller.signal)
      if (!controller.signal.aborted) consumers.value = result.data
    } catch (cause) {
      if (!controller.signal.aborted) consumersError.value = '用户列表读取失败，请重新展开重试'
    } finally {
      if (consumersController === controller) consumersLoading.value = false
    }
  }
  const loading = ref(false),
    error = ref(''),
    detail = ref(),
    detailOpen = ref(false)
  const detailLoading = ref(false),
    detailError = ref('')
  let listController,
    detailController,
    active = false
  let searchTimer, searchRevision = 0
  function closeDetail() {
    detailController?.abort()
    detailController = undefined
    detailOpen.value = false
    detail.value = undefined
    detailLoading.value = false
    detailError.value = ''
  }
  function clear() {
    clearTimeout(searchTimer)
    searchRevision += 1
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
    const revision = searchRevision
    if (!(await formRef.value?.validate().catch(() => false))) return
    if (revision !== searchRevision || !active) return
    page.value = 1
    await load()
  }
  async function reset() {
    Object.assign(filters, defaultFilters())
    clear()
    formRef.value?.clearValidate()
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
      const result = await (row.id == null ? getBillingSubject(row.subjectId, controller.signal) : getBillingEvent(row.id, controller.signal))
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
    consumersController?.abort()
    consumers.value = []
    clear()
  }
  watch(filters, () => {
    clear()
    if (!active || !allowed.value) return
    // 等待连续输入结束后查询；旧请求立即取消，避免返回过期筛选结果。
    loading.value = true
    searchTimer = setTimeout(() => { void search() }, 400)
  }, { flush: 'sync' })
  watch(() => [user.token, user.id, JSON.stringify(user.permissions)], () => {
    consumersController?.abort()
    consumers.value = []
    clear()
    if (active && allowed.value) void load()
  }, { flush: 'sync' })
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return {
    consumers, consumersLoading, consumersError, searchConsumers,
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
    reset,
    load,
    select,
    closeDetail,
  }
}
