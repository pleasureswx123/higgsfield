import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getProjects, type Project } from '@/api/projects'

// 侧栏独立于主列表筛选，只展示当前账号可见且未隐藏的项目。
export function useSidebarProjects() {
  const auth = useAuthStore()
  const route = useRoute()
  const projects = ref<Project[]>([])
  const loading = ref(false)
  const error = ref('')
  const hasMore = ref(false)
  let controller: AbortController | undefined
  async function load() {
    controller?.abort()
    const current = new AbortController()
    controller = current
    if (!auth.token || route.params.id) { loading.value = false; return }
    loading.value = true
    error.value = ''
    try {
      const result = await getProjects({ pageNum: 1, pageSize: 100, hidden: false, sort: 'name_asc' }, current.signal)
      if (current.signal.aborted) return
      projects.value = result.rows
      hasMore.value = result.hasNext
    } catch (cause) {
      if (!current.signal.aborted) {
        projects.value = []
        error.value = cause instanceof Error ? cause.message : '项目加载失败'
      }
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  watch(() => [auth.token, auth.user?.permissions.join('|')], () => {
    projects.value = []
    hasMore.value = false
    void load()
  }, { immediate: true, flush: 'sync' })
  watch(() => route.path, () => { void load() })
  onBeforeUnmount(() => controller?.abort())
  return { projects, loading, error, hasMore, load }
}
