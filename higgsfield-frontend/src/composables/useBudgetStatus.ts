import { onBeforeUnmount, ref, watch } from 'vue'
import { getBudgetStatus, type BudgetStatus } from '@/api/usage'

export function useBudgetStatus(project: () => string, refreshKey: () => string | undefined) {
  const status = ref<BudgetStatus>()
  const loading = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  async function refresh() {
    controller?.abort()
    status.value = undefined
    error.value = ''
    const identity = project()
    if (!identity) {
      loading.value = false
      return
    }
    const current = new AbortController()
    controller = current
    loading.value = true
    try {
      const response = await getBudgetStatus(identity, current.signal)
      if (!current.signal.aborted) status.value = response.data
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '预算状态读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  watch(
    [project, refreshKey],
    () => {
      void refresh()
    },
    { immediate: true },
  )
  onBeforeUnmount(() => {
    controller?.abort()
    status.value = undefined
  })
  return { status, loading, error, refresh }
}
