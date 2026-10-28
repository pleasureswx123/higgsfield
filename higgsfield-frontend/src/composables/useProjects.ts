import { ref, computed, onActivated, onDeactivated, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProjects, getProject, type Project, type ProjectStatus } from '@/api/projects'
import { useAuthStore } from '@/stores/auth'
export function useProjectPermissions() {
  const auth = useAuthStore()
  const canCreate = computed(
    () => auth.user?.permissions.some((p) => p === '*:*:*' || p === 'project:create') ?? false,
  )
  return { canCreate }
}
export function useProjects(recent = false) {
  const auth = useAuthStore()
  const route = useRoute(),
    router = useRouter()
  const rows = ref<Project[]>([]),
    loading = ref(false),
    error = ref(''),
    total = ref(0),
    page = ref(1)
  const search = ref(''),
    status = ref<ProjectStatus | ''>(''),
    sort = ref<'created_desc' | 'created_asc' | 'name_asc'>('created_desc')
  const hidden = ref(false), pinned = ref(false), collectionId = ref('')
  let controller: AbortController | undefined,
    sequence = 0,
    active = false
  async function load() {
    if (!active || !auth.token) return
    controller?.abort()
    controller = new AbortController()
    const ticket = ++sequence
    if (!recent) {
      search.value = typeof route.query.q === 'string' ? route.query.q : ''
      status.value = ['active', 'paused', 'archived', 'pending_delete'].includes(
        String(route.query.status),
      )
        ? (route.query.status as ProjectStatus)
        : ''
      sort.value = ['created_desc', 'created_asc', 'name_asc'].includes(String(route.query.sort))
        ? (route.query.sort as typeof sort.value)
        : 'created_desc'
      page.value = Math.max(1, Math.floor(Number(route.query.page) || 1))
      hidden.value = route.query.hidden === 'true'
      pinned.value = route.query.pinned === 'true'
      collectionId.value = typeof route.query.collectionId === 'string' && /^[1-9][0-9]{0,18}$/.test(route.query.collectionId)
        ? route.query.collectionId : ''
    }
    loading.value = true
    error.value = ''
    try {
      const result = await getProjects(
        {
          pageNum: recent ? 1 : page.value,
          pageSize: recent ? 4 : 20,
          q: search.value || undefined,
          status: status.value || undefined,
          sort: sort.value,
          hidden: hidden.value,
          pinned: pinned.value ? true : undefined,
          collectionId: collectionId.value || undefined,
        },
        controller.signal,
      )
      if (ticket === sequence) {
        const lastPage = Math.max(1, Math.ceil(result.total / 20))
        if (!recent && page.value > lastPage) {
          rows.value = []; total.value = result.total
          applyFilters(lastPage)
          return
        }
        rows.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (ticket === sequence && !controller.signal.aborted) {
        rows.value = []
        total.value = 0
        error.value = cause instanceof Error ? cause.message : '项目加载失败'
      }
    } finally {
      if (ticket === sequence) loading.value = false
    }
  }
  function applyFilters(nextPage = 1) {
    const query = {
      q: search.value.trim() || undefined,
      status: status.value || undefined,
      sort: sort.value,
      page: String(nextPage),
      hidden: hidden.value ? 'true' : undefined,
      pinned: pinned.value ? 'true' : undefined,
      collectionId: collectionId.value || undefined,
    }
    void router.replace({ path: '/projects', query })
  }
  watch(
    () => route.query,
    () => {
      if (active && !recent) void load()
    },
  )
  onActivated(() => {
    active = true
    void load()
  })
  onDeactivated(() => {
    active = false
    sequence++
    controller?.abort()
  })
  watch(() => [auth.token, auth.user?.permissions.join('|')], () => {
    sequence++
    controller?.abort()
    rows.value = []; total.value = 0; error.value = ''; loading.value = false
    if (active && auth.token) void load()
  }, { flush: 'sync' })
  onBeforeUnmount(() => { active = false; sequence++; controller?.abort() })
  return {
    rows,
    loading,
    error,
    total,
    page,
    search,
    status,
    sort,
    hidden,
    pinned,
    collectionId,
    load,
    applyFilters,
    ...useProjectPermissions(),
  }
}
export function useProjectDetail() {
  const route = useRoute()
  const project = ref<Project | null>(null),
    loading = ref(false),
    error = ref('')
  let controller: AbortController | undefined
  async function load() {
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = !project.value
    error.value = ''
    try {
      const result = await getProject(String(route.params.id), current.signal)
      if (!current.signal.aborted) project.value = result.data
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '项目加载失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  onActivated(load)
  onDeactivated(() => controller?.abort())
  onBeforeUnmount(() => controller?.abort())
  function acceptProject(value: Project) {
    if (value.id !== String(route.params.id)) return
    controller?.abort()
    project.value = value
    loading.value = false
    error.value = ''
  }
  return { project, loading, error, load, acceptProject }
}
