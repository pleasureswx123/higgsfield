import { onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import type { FormInstance } from 'element-plus'
import {
  getPersonalUsageSummary,
  getProjectUsageSummary,
  type UsageSummaryQuery,
  type UsageGroup,
  type UsageSummary,
} from '@/api/usage'
import { defaultUsageDates, usageWindow } from '@/utils/usage'

export function useUsageSummary(
  project: () => string | undefined = () => undefined,
  active: () => boolean = () => true,
) {
  const formRef = ref<FormInstance>()
  const filters = reactive({ dates: defaultUsageDates(), groupBy: 'project' as UsageGroup })
  const summary = ref<UsageSummary>()
  const loading = ref(false),
    error = ref('')
  let controller: AbortController | undefined
  let pageActive = false
  function clear() {
    controller?.abort()
    controller = undefined
    summary.value = undefined
    loading.value = false
    error.value = ''
  }
  async function load() {
    clear()
    if (!pageActive || !active()) return
    const current = new AbortController()
    controller = current
    try {
      const window = usageWindow(filters.dates || [])
      loading.value = true
      const params: UsageSummaryQuery = {
        ...window,
        groupBy: filters.groupBy,
        purpose: 'platform',
        timeBasis: 'createTime',
        businessTimezone: 'Asia/Shanghai',
      }
      const projectId = project()
      const response = projectId
        ? await getProjectUsageSummary(projectId, params, current.signal)
        : await getPersonalUsageSummary(params, current.signal)
      if (!current.signal.aborted) summary.value = response.data
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '用量读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  async function search() {
    clear()
    if (!(await formRef.value?.validate().catch(() => false))) return
    await load()
  }
  // 筛选改变即隐藏旧结果；保留筛选条件，重新进入页面时重新鉴权读取。
  watch(filters, clear, { flush: 'sync' })
  watch(
    [project, active],
    () => {
      void load()
    },
    { flush: 'sync' },
  )
  function activate() {
    if (pageActive) return
    pageActive = true
    void load()
  }
  onMounted(activate)
  onActivated(activate)
  onDeactivated(() => {
    pageActive = false
    clear()
  })
  onBeforeUnmount(clear)
  return { formRef, filters, summary, loading, error, search }
}
