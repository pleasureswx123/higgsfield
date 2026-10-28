import { computed, onActivated, onDeactivated, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessageBox, type FormInstance } from 'element-plus'
import { copyElement, type ElementDetail, type ElementRecord } from '@/api/elements'
import { getProjects, type Project } from '@/api/projects'
import { readBrief } from '@/api/projectWorkspace'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'

export function useElementCopy(value: ElementDetail, visible: () => boolean = () => true) {
  let mountedActive = true
  const source: ElementDetail = JSON.parse(JSON.stringify(value))
  const auth = useAuthStore(),
    active = ref(visible()),
    uncertain = ref(false)
  let epoch = 0,
    interaction = 0,
    alive = true
  const current = (ticket: number) => alive && ticket === epoch && Boolean(auth.token)
  const form = ref<FormInstance>(),
    fields = reactive({
      targetProjectId: source.element.projectId,
      name: source.element.name,
      alias: '',
    })
  const projects = ref<Project[]>([]),
    search = ref(''),
    projectPage = ref(1),
    total = ref(0),
    loading = ref(false),
    checking = ref(false),
    saving = ref(false)
  const locked = computed(() => saving.value || uncertain.value)
  let baseline = JSON.stringify(fields)
  const dirty = computed(() => !result.value && JSON.stringify(fields) !== baseline)
  const error = ref(''),
    permissionError = ref(''),
    result = ref<ElementRecord>(),
    targetAllowed = ref<string[]>([])
  const eligible = computed(
    () =>
      active.value &&
      Boolean(auth.token) &&
      !checking.value &&
      targetAllowed.value.includes('element:create') &&
      (fields.targetProjectId === source.element.projectId ||
        !source.currentRevision.media.length ||
        targetAllowed.value.includes('asset:create')),
  )
  const projectName = computed(
    () =>
      projects.value.find((project) => project.id === fields.targetProjectId)?.name ||
      `项目 ${fields.targetProjectId}`,
  )
  let searchController: AbortController | undefined,
    targetController: AbortController | undefined,
    intent:
      | {
          payload: {
            targetProjectId: string
            name: string
            alias: string
            sourceRevisionId: string
          }
          key: string
        }
      | undefined
  async function loadProjects() {
    if (!alive || !active.value || !auth.token || locked.value) return
    searchController?.abort()
    const controller = new AbortController()
    searchController = controller
    projects.value = []
    total.value = 0
    loading.value = true
    try {
      const response = await getProjects(
        { q: search.value, pageNum: projectPage.value, pageSize: 10, status: 'active' },
        controller.signal,
      )
      if (!controller.signal.aborted) {
        projects.value = response.rows
        total.value = response.total
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '项目加载失败'
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  function filter() {
    if (!active.value || !auth.token || locked.value) return
    if (projectPage.value !== 1) projectPage.value = 1
    else void loadProjects()
  }
  async function checkTarget(id: string) {
    if (!alive || !active.value || !auth.token) return
    targetController?.abort()
    targetAllowed.value = []
    permissionError.value = ''
    if (!id) {
      checking.value = false
      return
    }
    const controller = new AbortController()
    targetController = controller
    checking.value = true
    try {
      const response = await readBrief(id, controller.signal)
      if (!controller.signal.aborted) {
        targetAllowed.value = response.data.allowedActions
        if (!eligible.value && !targetAllowed.value.includes('element:create'))
          permissionError.value = '目标项目未授予元素创建权限或已不可编辑。'
        else if (
          id !== source.element.projectId &&
          source.currentRevision.media.length &&
          !targetAllowed.value.includes('asset:create')
        )
          permissionError.value = '复制图片到此项目还需要素材创建权限。'
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        permissionError.value = cause instanceof Error ? cause.message : '无法核验目标项目权限'
    } finally {
      if (!controller.signal.aborted) checking.value = false
    }
  }
  async function submit() {
    const ticket = epoch,
      viewTicket = interaction
    if (!active.value || !current(ticket) || saving.value || result.value || !eligible.value) return
    if (!intent) {
      const before = JSON.stringify(fields)
      if (!(await form.value?.validate().catch(() => false))) return
      if (
        !active.value ||
        viewTicket !== interaction ||
        !current(ticket) ||
        saving.value ||
        result.value ||
        !eligible.value ||
        before !== JSON.stringify(fields)
      )
        return
      intent = {
        payload: { ...fields, sourceRevisionId: source.currentRevision.id },
        key: crypto.randomUUID(),
      }
    }
    saving.value = true
    uncertain.value = true
    error.value = ''
    try {
      const response = await copyElement(source.element.id, intent.payload, intent.key)
      if (!current(ticket)) return
      result.value = response.data
      uncertain.value = false
      intent = undefined
    } catch (cause) {
      if (!current(ticket)) return
      const definitive =
        cause instanceof ApiError &&
        ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') ||
          (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
      if (definitive) {
        intent = undefined
        uncertain.value = false
      }
      error.value =
        (cause instanceof Error ? cause.message : '复制失败') +
        (definitive ? '；请检查目标项目、名称和别名后重试。' : '；结果尚未确定，请重试同一请求。')
    } finally {
      if (current(ticket)) saving.value = false
    }
  }
  watch(() => fields.targetProjectId, checkTarget, { immediate: true, flush: 'sync' })
  watch(projectPage, () => {
    void loadProjects()
  })
  function clear() {
    epoch++
    interaction++
    searchController?.abort()
    targetController?.abort()
    targetAllowed.value = []
    projects.value = []
    result.value = undefined
    saving.value = false
    uncertain.value = false
    checking.value = false
    loading.value = false
    total.value = 0
    error.value = ''
    permissionError.value = ''
    intent = undefined
    fields.targetProjectId = ''
    fields.name = ''
    fields.alias = ''
    baseline = JSON.stringify(fields)
  }
  watch(
    () => auth.token,
    () => {
      clear()
      if (active.value && auth.token) void loadProjects()
    },
    { flush: 'sync' },
  )
  watch(
    () => JSON.stringify(auth.user?.permissions || []),
    () => {
      interaction++
      targetAllowed.value = []
      searchController?.abort()
      projects.value = []
      total.value = 0
      loading.value = false
      if (active.value && auth.token)
        void checkTarget(intent?.payload.targetProjectId || fields.targetProjectId)
      void loadProjects()
    },
    { flush: 'sync' },
  )
  function suspend() {
    if (!active.value) return
    active.value = false
    interaction++
    searchController?.abort()
    targetController?.abort()
    projects.value = []
    targetAllowed.value = []
    loading.value = false
    checking.value = false
  }
  function resume() {
    if (active.value || !mountedActive || !visible()) return
    active.value = true
    void checkTarget(intent?.payload.targetProjectId || fields.targetProjectId)
    void loadProjects()
  }
  onDeactivated(() => {
    mountedActive = false
    suspend()
  })
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(visible, value => value ? resume() : suspend(), { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    clear()
  })
  async function confirmClose() {
    if (locked.value) return false
    if (!dirty.value) return true
    const ticket = epoch,
      view = interaction
    try {
      await ElMessageBox.confirm('尚未提交的复制配置将被丢弃。', '关闭元素复制', {
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
      })
      return current(ticket) && view === interaction && !locked.value
    } catch {
      return false
    }
  }
  onBeforeRouteLeave(confirmClose)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || confirmClose())
  void loadProjects()
  return {
    active,
    locked,
    dirty,
    confirmClose,
    uncertain,
    form,
    fields,
    projects,
    search,
    projectPage,
    total,
    loading,
    checking,
    saving,
    error,
    permissionError,
    result,
    eligible,
    projectName,
    filter,
    submit,
  }
}
