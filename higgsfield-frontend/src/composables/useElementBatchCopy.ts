import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox, type FormInstance } from 'element-plus'
import { copyElement, readElement, type ElementRecord } from '@/api/elements'
import { getProjects, type Project } from '@/api/projects'
import { readBrief } from '@/api/projectWorkspace'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

type Payload = Parameters<typeof copyElement>[1]
interface CopyRow {
  id: string
  projectId: string
  sourceRevisionId: string
  hasMedia: boolean
  name: string
  alias: string
  error: string
  result?: ElementRecord
  intent?: { payload: Payload; key: string }
}

export function useElementBatchCopy(allowed: () => boolean, changed: (ids: string[]) => void, visible: () => boolean = () => true) {
  let mountedActive = true
  const auth = useAuthStore(),
    active = ref(visible()),
    opened = ref(false)
  const form = ref<FormInstance>(),
    fields = reactive({ targetProjectId: '', items: [] as CopyRow[] })
  const projects = ref<Project[]>([]),
    search = ref(''),
    page = ref(1),
    total = ref(0)
  const loading = ref(false),
    searching = ref(false),
    checking = ref(false),
    saving = ref(false)
  const error = ref(''),
    targetAllowed = ref<string[]>([])
  const uncertain = computed(() => fields.items.some((item) => item.intent))
  const locked = computed(() => saving.value || uncertain.value)
  const remaining = computed(() => fields.items.filter((item) => !item.result))
  let initialTarget = '',
    initialRows: Record<string, string> = {}
  const dirty = computed(
    () =>
      opened.value &&
      remaining.value.length > 0 &&
      (fields.targetProjectId !== initialTarget ||
        remaining.value.some(
          (item) => JSON.stringify([item.name, item.alias]) !== initialRows[item.id],
        )),
  )
  const eligible = computed(
    () =>
      active.value &&
      opened.value &&
      !!auth.token &&
      allowed() &&
      !loading.value &&
      !checking.value &&
      targetAllowed.value.includes('element:create') &&
      remaining.value.length > 0 &&
      remaining.value.every(
        (item) =>
          item.projectId === fields.targetProjectId ||
          !item.hasMedia ||
          targetAllowed.value.includes('asset:create'),
      ),
  )
  let epoch = 0,
    interaction = 0,
    alive = true,
    deferred: string[] = []
  let reader: AbortController | undefined,
    searcher: AbortController | undefined,
    checker: AbortController | undefined
  const valid = (ticket: number) => alive && ticket === epoch && !!auth.token
  function clear() {
    epoch++
    interaction++
    reader?.abort()
    searcher?.abort()
    checker?.abort()
    opened.value = false
    loading.value = false
    searching.value = false
    checking.value = false
    saving.value = false
    fields.items = []
    fields.targetProjectId = ''
    projects.value = []
    targetAllowed.value = []
    search.value = ''
    page.value = 1
    total.value = 0
    error.value = ''
    deferred = []
    initialTarget = ''
    initialRows = {}
  }
  async function loadProjects() {
    if (!active.value || !opened.value || !auth.token || !allowed() || locked.value) return
    searcher?.abort()
    const controller = (searcher = new AbortController())
    projects.value = []
    total.value = 0
    searching.value = true
    try {
      const response = await getProjects(
        { q: search.value, pageNum: page.value, pageSize: 10, status: 'active' },
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
      if (!controller.signal.aborted) searching.value = false
    }
  }
  function filter() {
    if (page.value !== 1) page.value = 1
    else void loadProjects()
  }
  async function checkTarget() {
    checker?.abort()
    targetAllowed.value = []
    checking.value = false
    if (!active.value || !opened.value || !auth.token || !fields.targetProjectId) return
    const controller = (checker = new AbortController())
    checking.value = true
    try {
      const response = await readBrief(fields.targetProjectId, controller.signal)
      if (!controller.signal.aborted) targetAllowed.value = response.data.allowedActions
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '无法核验目标权限'
    } finally {
      if (!controller.signal.aborted) checking.value = false
    }
  }
  async function open(items: ElementRecord[]) {
    if (!alive || !active.value || !auth.token || !allowed() || locked.value) return
    const previous = epoch
    if (
      !(await confirmClose()) ||
      previous !== epoch ||
      !active.value ||
      !allowed() ||
      locked.value
    )
      return
    clear()
    const sources = JSON.parse(
      JSON.stringify([
        ...new Map(
          items
            .filter((item) => !item.allowedActions || item.allowedActions.includes('element:copy'))
            .map((item) => [item.id, item]),
        ).values(),
      ]),
    ) as ElementRecord[]
    if (!sources.length) return
    opened.value = true
    loading.value = true
    fields.targetProjectId = sources[0]!.projectId
    const ticket = epoch,
      controller = (reader = new AbortController())
    void loadProjects()
    try {
      const loaded: CopyRow[] = []
      for (const source of sources) {
        const { data } = await readElement(source.id, controller.signal)
        if (!valid(ticket) || controller.signal.aborted) return
        if (
          data.element.projectId !== source.projectId ||
          data.currentRevision.id !== source.currentRevisionId
        )
          throw new Error('所选元素已变化，请关闭并刷新列表后重新选择。')
        if (data.element.allowedActions && !data.element.allowedActions.includes('element:copy'))
          throw new Error('所选元素已无复制权限，请刷新列表。')
        loaded.push({
          id: source.id,
          projectId: source.projectId,
          sourceRevisionId: data.currentRevision.id,
          hasMedia: data.currentRevision.media.length > 0,
          name: `Copy of ${data.element.name}`.slice(0, 200),
          alias: '',
          error: '',
        })
      }
      fields.items = loaded
      initialTarget = fields.targetProjectId
      initialRows = Object.fromEntries(
        loaded.map((item) => [item.id, JSON.stringify([item.name, item.alias])]),
      )
    } catch (cause) {
      if (valid(ticket) && !controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '元素读取失败'
    } finally {
      if (valid(ticket) && !controller.signal.aborted) loading.value = false
    }
  }
  async function submit() {
    if (saving.value || !eligible.value) return
    const ticket = epoch,
      view = interaction,
      before = JSON.stringify(fields)
    if (!(await form.value?.validate().catch(() => false))) return
    if (
      !valid(ticket) ||
      view !== interaction ||
      saving.value ||
      !eligible.value ||
      before !== JSON.stringify(fields)
    )
      return
    const aliases = remaining.value.map((item) => item.alias.trim())
    if (new Set(aliases).size !== aliases.length) {
      error.value = '待复制元素的别名不能重复。'
      return
    }
    // 未成功项各自保留固定意图；未知结果绝不更换键或内容。
    for (const item of remaining.value)
      item.intent ||= {
        payload: {
          targetProjectId: fields.targetProjectId,
          sourceRevisionId: item.sourceRevisionId,
          name: item.name.trim(),
          alias: item.alias.trim(),
        },
        key: crypto.randomUUID(),
      }
    const items = [...remaining.value],
      completed: string[] = []
    saving.value = true
    error.value = ''
    try {
      for (const item of items) {
        if (!valid(ticket) || view !== interaction || !eligible.value) break
        const intent = item.intent!
        item.error = ''
        try {
          const response = await copyElement(item.id, intent.payload, intent.key)
          if (!valid(ticket)) return
          item.result = response.data
          item.intent = undefined
          completed.push(item.id)
        } catch (cause) {
          if (!valid(ticket)) return
          const definitive =
            cause instanceof ApiError &&
            ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') ||
              (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
          if (definitive) item.intent = undefined
          item.error =
            (cause instanceof Error ? cause.message : '复制失败') +
            (definitive ? '；可修改后重试。' : '；结果未知，重试将使用原请求。')
        }
      }
    } finally {
      if (valid(ticket)) {
        saving.value = false
        if (completed.length) {
          if (active.value) changed(completed)
          else deferred.push(...completed)
        }
      }
    }
  }
  async function confirmClose() {
    if (locked.value) return false
    if (!dirty.value) return true
    const ticket = epoch,
      view = interaction
    try {
      await ElMessageBox.confirm(
        '未完成条目的复制配置将被丢弃，已成功复制的元素仍会保留。',
        '关闭批量复制',
        {
          confirmButtonText: '放弃修改',
          cancelButtonText: '继续编辑',
        },
      )
      return valid(ticket) && view === interaction && !locked.value
    } catch {
      return false
    }
  }
  async function close() {
    const ticket = epoch
    if ((await confirmClose()) && valid(ticket) && !locked.value) clear()
  }
  watch(
    () => fields.targetProjectId,
    () => void checkTarget(),
    { flush: 'sync' },
  )
  watch(page, () => void loadProjects())
  watch(() => auth.token, clear, { flush: 'sync' })
  watch(
    () => [allowed(), JSON.stringify(auth.user?.permissions || [])],
    () => {
      interaction++
      searcher?.abort()
      projects.value = []
      total.value = 0
      searching.value = false
      void checkTarget()
      void loadProjects()
    },
    { flush: 'sync' },
  )
  function suspend() {
    if (!active.value) return
    active.value = false
    interaction++
    reader?.abort()
    searcher?.abort()
    checker?.abort()
    loading.value = false
    searching.value = false
    checking.value = false
    targetAllowed.value = []
    projects.value = []
  }
  function resume() {
    if (active.value || !mountedActive || !visible()) return
    active.value = true
    if (deferred.length) {
      const ids = deferred
      deferred = []
      changed(ids)
    }
    void checkTarget()
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
  onBeforeRouteLeave(confirmClose)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || confirmClose())
  return {
    active,
    opened,
    fields,
    form,
    projects,
    search,
    page,
    total,
    loading,
    searching,
    checking,
    saving,
    error,
    eligible,
    locked,
    dirty,
    confirmClose,
    uncertain,
    remaining,
    open,
    close,
    filter,
    submit,
  }
}
