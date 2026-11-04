import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getProjects, type Project } from '@/api/projects'
import { useProjectUpdatesStore } from '@/stores/projectUpdates'

// 侧栏独立于主列表筛选，展示当前账号可见且未隐藏的全部项目。
export function useSidebarProjects() {
  const auth = useAuthStore()
  const updates = useProjectUpdatesStore()
  const route = useRoute()
  const projects = ref<Project[]>([])
  const loading = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  async function load() {
    controller?.abort()
    const current = new AbortController()
    controller = current
    if (!auth.token || route.params.id) { loading.value = false; return }
    loading.value = true
    error.value = ''
    try {
      const collected = new Map<string, Project>()
      let pageNum = 1
      while (true) {
        const result = await getProjects({ pageNum, pageSize: 100, hidden: false, sort: 'name_asc' }, current.signal)
        if (current.signal.aborted) return
        for (const project of result.rows) collected.set(project.id, project)
        if (!result.hasNext || !result.rows.length) break
        pageNum++
      }
      projects.value = [...collected.values()]
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
    void load()
  }, { immediate: true, flush: 'sync' })
  watch(() => route.path, () => { void load() })
  watch(() => updates.revision, () => { void load() })
  onBeforeUnmount(() => controller?.abort())
  return { projects, loading, error, load }
}
