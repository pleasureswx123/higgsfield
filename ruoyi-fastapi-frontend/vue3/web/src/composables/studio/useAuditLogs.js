import { computed, reactive, ref, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import { listAuditLogs } from '@/api/studio/audit'
import { toRfc3339 } from '@/utils/time'
import { validRoutingId } from '@/utils/routing'

export function useAuditLogs() {
  const user = useUserStore()
  const allowed = computed(() => user.permissions.includes('*:*:*') || user.permissions.includes('audit:read'))
  const filters = reactive({ objectType: '', objectId: '', actorId: '', from: '', to: '' })
  const rows = ref([]), page = ref(1), total = ref(0), loading = ref(false), error = ref(''), selected = ref()
  let active = false, controller
  function clear() {
    controller?.abort()
    controller = undefined
    rows.value = []
    total.value = 0
    selected.value = undefined
    loading.value = false
    error.value = ''
  }
  async function load() {
    clear()
    if (!active || !allowed.value) return
    const current = new AbortController()
    controller = current
    loading.value = true
    try {
      const params = { pageNum: page.value, pageSize: 20 }
      for (const field of ['objectType', 'objectId', 'actorId']) {
        if (filters[field].trim()) params[field] = filters[field].trim()
      }
      if (params.actorId && !validRoutingId(params.actorId)) throw new Error('操作者ID须为有效的正整数标识')
      for (const field of ['from', 'to']) {
        if (filters[field]) params[field] = toRfc3339(filters[field], { timezoneName: 'Asia/Shanghai' })
      }
      if (params.from && params.to && Date.parse(params.from) >= Date.parse(params.to))
        throw new Error('结束时间必须晚于开始时间')
      const result = await listAuditLogs(params, current.signal)
      if (controller === current) {
        rows.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (controller === current) error.value = cause?.message || '业务审计读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  function search() { page.value = 1; return load() }
  function inspect(row) {
    if (active && allowed.value && rows.value.includes(row)) selected.value = row
  }
  function activate() { if (!active) { active = true; load() } }
  function deactivate() { active = false; clear() }
  watch(filters, () => { clear(); page.value = 1 }, { flush: 'sync' })
  watch(allowed, (value) => { if (!value) clear(); else if (active) load() }, { flush: 'sync' })
  onMounted(activate)
  onActivated(activate)
  onDeactivated(deactivate)
  onBeforeUnmount(deactivate)
  return { allowed, filters, rows, page, total, loading, error, selected, load, search, inspect }
}
