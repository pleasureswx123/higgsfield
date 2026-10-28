import { computed, ref, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  readBrief,
  saveBrief,
  readMembers,
  readRoles,
  type Brief,
  type BriefBody,
  type Member,
  type ProjectRole,
} from '@/api/projectWorkspace'

const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : '操作失败，请稍后重试'
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value))
export function useProjectWorkspace(id: string) {
  const brief = ref<Brief>(),
    draft = ref<BriefBody>({ schemaVersion: 1, type: 'doc', content: [] })
  const loading = ref(true),
    error = ref(''),
    saving = ref(false),
    notice = ref('')
  const dirty = computed(
    () => !!brief.value && JSON.stringify(draft.value) !== JSON.stringify(brief.value.body),
  )
  const canEdit = computed(() => brief.value?.allowedActions.includes('project:edit') ?? false)
  const canReadMembers = computed(
    () => brief.value?.allowedActions.includes('member:read') ?? false,
  )
  const canManage = computed(() => brief.value?.allowedActions.includes('member:manage') ?? false)
  let alive = true,
    active = true,
    epoch = 0,
    readSequence = 0,
    initialized = false,
    saveKey = '',
    savedPayload = ''
  let reader: AbortController | undefined, writer: AbortController | undefined
  function invalidate(clearContent = false) {
    epoch++
    readSequence++
    reader?.abort()
    writer?.abort()
    loading.value = false
    saving.value = false
    error.value = ''
    notice.value = ''
    if (brief.value) brief.value.allowedActions = []
    if (clearContent) {
      brief.value = undefined
      draft.value = { schemaVersion: 1, type: 'doc', content: [] }
      saveKey = ''
      savedPayload = ''
    }
  }
  async function load(replaceDraft = false) {
    if (!alive || !active || saving.value) return
    reader?.abort()
    const current = new AbortController(), ticket = ++readSequence
    reader = current
    const originalDraft = JSON.stringify(draft.value)
    loading.value = !brief.value
    error.value = ''
    try {
      const result = await readBrief(id, current.signal)
      if (!alive || current.signal.aborted || ticket !== readSequence) return
      // 后台刷新不重置未保存正文或其基准版本。
      if (dirty.value && (!replaceDraft || JSON.stringify(draft.value) !== originalDraft)) {
        if (brief.value) brief.value.allowedActions = result.data.allowedActions
        return
      }
      brief.value = result.data
      draft.value = copy(result.data.body)
    } catch (cause) {
      if (current.signal.aborted || ticket !== readSequence) return
      if (cause instanceof ApiError && [401, 403].includes(cause.code)) invalidate(true)
      else if (brief.value) brief.value.allowedActions = []
      error.value = message(cause)
    } finally {
      if (!current.signal.aborted && ticket === readSequence) loading.value = false
    }
  }
  async function reload() {
    const stamp = epoch
    if (saving.value) return
    if (dirty.value) {
      try {
        await ElMessageBox.confirm('重新加载会丢弃未保存修改。是否继续？', '重新加载简报', {
          confirmButtonText: '重新加载',
          cancelButtonText: '保留草稿',
        })
      } catch {
        return
      }
    }
    if (stamp === epoch && !saving.value) await load(true)
  }
  async function save() {
    if (!alive || !active || !brief.value || saving.value || !canEdit.value) return
    reader?.abort()
    readSequence++
    loading.value = false
    const stamp = epoch, current = new AbortController()
    writer = current
    const payload = { revision: brief.value.revision, body: copy(draft.value) }
    const serialized = JSON.stringify(payload)
    if (serialized !== savedPayload) {
      saveKey = crypto.randomUUID()
      savedPayload = serialized
    }
    saving.value = true
    error.value = ''
    notice.value = ''
    try {
      const result = await saveBrief(id, payload, saveKey, current.signal)
      if (stamp !== epoch || current.signal.aborted) return
      brief.value = result.data
      if (JSON.stringify(draft.value) === JSON.stringify(payload.body)) draft.value = copy(result.data.body)
      notice.value = dirty.value ? '简报已保存；后续修改尚未保存' : '简报已保存'
    } catch (cause) {
      if (stamp !== epoch || current.signal.aborted) return
      if (cause instanceof ApiError && [401, 403].includes(cause.code)) invalidate(true)
      error.value = message(cause)
    } finally {
      if (stamp === epoch) saving.value = false
    }
  }
  const unload = (event: BeforeUnloadEvent) => {
    if (dirty.value || saving.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => {
    initialized = true
    void load()
    window.addEventListener('beforeunload', unload)
  })
  onActivated(() => {
    const resume = !active
    active = true
    if (initialized && resume) void load()
  })
  onDeactivated(() => { active = false; invalidate() })
  watch(() => useAuthStore().token, () => invalidate(true), { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    invalidate(true)
    window.removeEventListener('beforeunload', unload)
  })
  async function confirmLeave() {
    const stamp = epoch
    if (saving.value) return false
    if (!dirty.value) return true
    try {
      await ElMessageBox.confirm(
        '简报尚未保存，请先保存需要保留的内容。是否离开？',
        '未保存的修改',
        { confirmButtonText: '离开', cancelButtonText: '继续编辑' },
      )
      return stamp === epoch && !saving.value
    } catch {
      return false
    }
  }
  onBeforeRouteLeave(confirmLeave)
  onBeforeRouteUpdate((to, from) => to.params.id === from.params.id ? true : confirmLeave())
  return {
    brief,
    draft,
    dirty,
    loading,
    error,
    saving,
    notice,
    canEdit,
    canReadMembers,
    canManage,
    load,
    reload,
    save,
  }
}

export function useProjectMembers(id: string) {
  const members = ref<Member[]>([]),
    roles = ref<ProjectRole[]>([]),
    total = ref(0),
    page = ref(1)
  const status = ref<'active' | 'removed'>('active'),
    loading = ref(false),
    error = ref('')
  let sequence = 0,
    alive = true,
    active = true,
    initialized = false
  let controller: AbortController | undefined
  function clear() {
    sequence++
    controller?.abort()
    members.value = []
    roles.value = []
    total.value = 0
    loading.value = false
    error.value = ''
  }
  async function load() {
    if (!alive || !active) return
    controller?.abort()
    const current = new AbortController()
    controller = current
    const ticket = ++sequence
    const requestedStatus = status.value
    let requestedPage = page.value
    loading.value = true
    error.value = ''
    members.value = []
    roles.value = []
    total.value = 0
    try {
      const [firstList, roleList] = await Promise.all([
        readMembers(id, requestedPage, requestedStatus, current.signal),
        readRoles(id, current.signal),
      ])
      if (!alive || ticket !== sequence || current.signal.aborted) return
      let list = firstList
      // 后台成员变更可能让末页消失；在同一次加载内回退，保持筛选与取消边界。
      while (requestedPage > Math.max(1, Math.ceil(list.total / 20))) {
        requestedPage = Math.max(1, Math.ceil(list.total / 20))
        page.value = requestedPage
        if (list.total === 0) break
        list = await readMembers(id, requestedPage, requestedStatus, current.signal)
        if (!alive || ticket !== sequence || current.signal.aborted) return
      }
      members.value = list.rows
      roles.value = roleList.data.items
      total.value = list.total
    } catch (cause) {
      if (alive && ticket === sequence) {
        error.value = message(cause)
        members.value = []
        roles.value = []
      }
    } finally {
      if (alive && ticket === sequence) loading.value = false
    }
  }
  function changeStatus(value: 'active' | 'removed') {
    status.value = value
    page.value = 1
    void load()
  }
  function changePage(value: number) {
    if (!Number.isSafeInteger(value) || value < 1 || value === page.value) return
    page.value = value
    void load()
  }
  onMounted(() => { initialized = true; void load() })
  onDeactivated(() => { active = false; clear() })
  onActivated(() => {
    const resume = !active
    active = true
    if (initialized && resume) void load()
  })
  watch(() => useAuthStore().token, () => {
    clear()
    page.value = 1
  }, { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    clear()
  })
  return { members, roles, total, page, status, loading, error, load, changeStatus, changePage }
}
