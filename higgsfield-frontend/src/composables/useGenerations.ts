import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { libraryWindow } from '@/utils/libraryWindow'
import {
  listGenerations,
  type GenerationKind,
  type GenerationState,
  type GenerationSummary,
} from '@/api/generations'

export function useGenerations(projectId: () => string | undefined, active: () => boolean, projectFilter: () => string | undefined = () => undefined) {
  const auth = useAuthStore()
  const rows = ref<GenerationSummary[]>([]),
    total = ref(0),
    page = ref(1)
  const kind = ref<GenerationKind | ''>(''),
    state = ref<GenerationState | ''>('')
  const dates = ref<string[] | null>(null)
  const loading = ref(false),
    error = ref('')
  let controller: AbortController | undefined
  let deactivated = false
  let alive = true
  function clear() {
    controller?.abort()
    rows.value = []
    total.value = 0
    loading.value = false
    error.value = ''
  }
  async function refresh() {
    clear()
    if (!alive || !active() || deactivated || !auth.token) return
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = ''
    rows.value = []
    total.value = 0
    try {
      const result = await listGenerations(
        {
          scope: projectId() ? 'project' : 'mine',
          projectId: projectId() || projectFilter(),
          pageNum: page.value,
          pageSize: 20,
          kind: kind.value || undefined,
          state: state.value || undefined,
          ...libraryWindow(dates.value),
        },
        current.signal,
      )
      if (!current.signal.aborted) {
        rows.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '生成记录加载失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  watch([projectId, projectFilter, kind, state, dates], () => {
    page.value = 1
  })
  watch(
    [projectId, projectFilter, active, page, kind, state, dates],
    () => {
      void refresh()
    },
    { immediate: true },
  )
  watch(
    () => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions || [])],
    () => {
      clear()
      if (page.value !== 1) page.value = 1
      else void refresh()
    },
    { flush: 'sync' },
  )
  watch(active, (value) => { if (!value) clear() }, { flush: 'sync' })
  onDeactivated(() => {
    deactivated = true
    clear()
  })
  onActivated(() => {
    if (deactivated) {
      deactivated = false
      void refresh()
    }
  })
  onBeforeUnmount(() => { alive = false; clear() })
  return { rows, total, page, kind, state, dates, loading, error, refresh }
}
