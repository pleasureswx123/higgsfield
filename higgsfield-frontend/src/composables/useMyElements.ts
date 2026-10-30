import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import {
  listElements,
  type ElementCategory,
  type ElementRecord,
  type WorkStatus,
} from '@/api/elements'
import { useAuthStore } from '@/stores/auth'

export function useMyElements() {
  const auth = useAuthStore()
  let active = true,
    adjustingPage = false
  const mineFilter = ref<'all' | 'created' | 'favorites'>('created')
  const workStatus = ref<'' | WorkStatus>(''),
    statusGroup = ref<'' | 'active' | 'drafts'>('')
  const rows = ref<ElementRecord[]>([]),
    total = ref(0),
    page = ref(1)
  const search = ref(''),
    category = ref<'' | ElementCategory>('')
  const loading = ref(false),
    error = ref('')
  const hasFilters = computed(() =>
    Boolean(
      search.value.trim() ||
      category.value ||
      workStatus.value ||
      statusGroup.value ||
      mineFilter.value !== 'created',
    ),
  )
  const filteredResult = ref(false)
  function clearFilters() {
    search.value = ''
    category.value = ''
    workStatus.value = ''
    statusGroup.value = ''
    mineFilter.value = 'created'
    filter()
  }
  let controller: AbortController | undefined
  async function refresh() {
    if (!active || !auth.token) return
    controller?.abort()
    const filtered = hasFilters.value
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = ''
    rows.value = []
    try {
      const result = await listElements(
        undefined,
        {
          scope: 'mine',
          mineFilter: mineFilter.value,
          pageNum: page.value,
          pageSize: 30,
          q: search.value,
          category: category.value || undefined,
          workStatus: workStatus.value || undefined,
          statusGroup: statusGroup.value || undefined,
        },
        current.signal,
      )
      if (!current.signal.aborted) {
        filteredResult.value = filtered
        total.value = result.total
        const lastPage = Math.max(1, Math.ceil(result.total / 30))
        if (page.value > lastPage) {
          // 总数减少时等待有效页结果，避免页码显示与列表内容不一致。
          adjustingPage = true
          page.value = lastPage
          adjustingPage = false
          if (result.total > 0) {
            await refresh()
            return
          }
        }
        rows.value = result.rows
      }
    } catch (cause) {
      if (!current.signal.aborted) {
        total.value = 0
        error.value = cause instanceof Error ? cause.message : '元素加载失败'
      }
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  function filter() {
    if (page.value !== 1) page.value = 1
    else void refresh()
  }
  watch(
    page,
    () => {
      if (!adjustingPage) void refresh()
    },
    { flush: 'sync' },
  )
  function clear() {
    controller?.abort()
    rows.value = []
    total.value = 0
    loading.value = false
    error.value = ''
  }
  onMounted(() => {
    void refresh()
  })
  onActivated(() => {
    if (!active) {
      active = true
      void refresh()
    }
  })
  onDeactivated(() => {
    active = false
    clear()
  })
  watch(
    () => [auth.token, JSON.stringify(auth.user?.permissions || [])],
    () => {
      clear()
      if (active) void refresh()
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(() => {
    active = false
    clear()
  })
  return {
    mineFilter,
    hasFilters,
    filteredResult,
    clearFilters,
    rows,
    total,
    page,
    search,
    category,
    workStatus,
    statusGroup,
    loading,
    error,
    refresh,
    filter,
  }
}
