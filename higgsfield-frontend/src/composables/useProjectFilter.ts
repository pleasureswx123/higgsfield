import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { getProjects, type Project } from '@/api/projects'
import { useAuthStore } from '@/stores/auth'

/** 项目筛选只读取当前可见项目，不以选择结果授予任务访问权限。 */
export function useProjectFilter(enabled: () => boolean, clearSelection: () => void) {
  const auth = useAuthStore()
  const opened = ref(false), q = ref(''), page = ref(1), total = ref(0)
  const rows = ref<Project[]>([]), loading = ref(false), error = ref('')
  let active = true, alive = true, controller: AbortController | undefined
  function clear() {
    controller?.abort()
    rows.value = []
    total.value = 0
    loading.value = false
    error.value = ''
  }
  async function load() {
    clear()
    if (!alive || !active || !enabled() || !opened.value || !auth.token) return
    const current = controller = new AbortController()
    loading.value = true
    try {
      const result = await getProjects({ q: q.value.trim() || undefined, pageNum: page.value, pageSize: 10 }, current.signal)
      if (current.signal.aborted) return
      rows.value = result.rows
      total.value = result.total
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '项目读取失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  function search() {
    if (page.value !== 1) page.value = 1
    else void load()
  }
  watch([opened, page], () => void load())
  watch(enabled, value => { if (!value) { opened.value = false; clear() } }, { flush: 'sync' })
  watch(() => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions || [])], () => {
    opened.value = false
    clear()
    clearSelection()
    q.value = ''
    page.value = 1
  }, { flush: 'sync' })
  onDeactivated(() => { active = false; opened.value = false; clear() })
  onActivated(() => { active = true })
  onBeforeUnmount(() => { alive = false; clear() })
  return { opened, q, page, rows, total, loading, error, search, load }
}
