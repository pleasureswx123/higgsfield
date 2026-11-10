import { computed, reactive, ref, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import { listProviderCalls, getProviderCall, listCallTasks, getTaskCalls } from '@/api/studio/providerCalls'
import { toRfc3339 } from '@/utils/time'
import { validRoutingId } from '@/utils/routing'

export function useProviderCalls() {
  const user = useUserStore()
  const allowed = computed(() => user.permissions.includes('*:*:*') || user.permissions.includes('operations:read'))
  const filters = reactive({ jobId: '', accountId: '', state: '', from: '', to: '' })
  const rows = ref([]), page = ref(1), total = ref(0), loading = ref(false), error = ref('')
  const selectedId = ref(''), detail = ref(), detailLoading = ref(false), detailError = ref('')
  const view = ref('tasks'), processId = ref(''), processRows = ref([]), processLoading = ref(false), processError = ref('')
  let active = false, controller, detailController, processController
  function closeProcess() {
    processController?.abort()
    processController = undefined
    processId.value = ''; processRows.value = []; processLoading.value = false; processError.value = ''
    close()
  }
  async function inspectProcess(id) {
    closeProcess()
    if (!active || !allowed.value) return
    processId.value = String(id)
    const current = new AbortController()
    processController = current
    processLoading.value = true
    try {
      const result = await getTaskCalls(id, current.signal)
      if (processController === current) processRows.value = result.data
    } catch (cause) {
      if (processController === current) processError.value = cause?.message || '执行过程读取失败'
    } finally {
      if (processController === current) processLoading.value = false
    }
  }
  function close() {
    detailController?.abort()
    detailController = undefined
    selectedId.value = ''
    detail.value = undefined
    detailLoading.value = false
    detailError.value = ''
  }
  function clear() {
    controller?.abort()
    controller = undefined
    rows.value = []
    total.value = 0
    loading.value = false
    error.value = ''
    closeProcess()
  }
  async function load() {
    clear()
    if (!active || !allowed.value) return
    const current = new AbortController()
    controller = current
    loading.value = true
    try {
      const params = { pageNum: page.value, pageSize: 20 }
      for (const field of ['jobId', 'accountId']) {
        const value = filters[field].trim()
        if (value && !validRoutingId(value)) throw new Error('任务编号和账号ID须为有效的正整数')
        if (value) params[field] = value
      }
      if (filters.state) params.state = filters.state
      for (const field of ['from', 'to']) {
        if (filters[field]) params[field] = toRfc3339(filters[field], { timezoneName: 'Asia/Shanghai' })
      }
      if (params.from && params.to && Date.parse(params.from) >= Date.parse(params.to)) throw new Error('结束时间必须晚于开始时间')
      const result = await (view.value === 'tasks' ? listCallTasks : listProviderCalls)(params, current.signal)
      if (controller === current) { rows.value = result.rows; total.value = result.total }
    } catch (cause) {
      if (controller === current) error.value = cause?.message || '调用记录读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  async function inspect(id) {
    close()
    if (!active || !allowed.value || !(view.value === 'calls' && rows.value.some(row => row.id === id)) && !processRows.value.some(row => row.id === id)) return
    selectedId.value = id
    const current = new AbortController()
    detailController = current
    detailLoading.value = true
    try {
      const result = await getProviderCall(id, current.signal)
      if (detailController === current) detail.value = result.data
    } catch (cause) {
      if (detailController === current) detailError.value = cause?.message || '调用证据读取失败'
    } finally {
      if (detailController === current) detailLoading.value = false
    }
  }
  function search() { page.value = 1; return load() }
  function reset() {
    Object.assign(filters, { jobId: '', accountId: '', state: '', from: '', to: '' })
    return search()
  }
  function activate() { if (!active) { active = true; load() } }
  function deactivate() { active = false; clear() }
  watch(filters, () => { clear(); page.value = 1 }, { flush: 'sync' })
  watch(view, search)
  watch(allowed, value => { if (!value) clear(); else if (active) load() }, { flush: 'sync' })
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return { allowed, filters, rows, page, total, loading, error, selectedId, detail, detailLoading, detailError, load, search, reset, inspect, close,
    view, processId, processRows, processLoading, processError, inspectProcess, closeProcess }
}
