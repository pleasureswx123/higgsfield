import { onActivated, onDeactivated, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  listElements,
  listElementTrash,
  recycleElement,
  type ElementCategory,
  type ElementRecord,
  type RecycledElement,
  type WorkStatus,
} from '@/api/elements'

export function useElements(projectId: string, visible: () => boolean = () => true) {
  const auth = useAuthStore()
  let epoch = 0, interaction = 0, alive = true, active = visible(), mountedActive = true
  const currentSession = (ticket: number) => alive && ticket === epoch && Boolean(auth.token)
  const rows = ref<ElementRecord[]>([]),
    recycled = ref<RecycledElement[]>([]),
    total = ref(0),
    page = ref(1)
  const search = ref(''),
    category = ref<'' | ElementCategory>(''),
    group = ref<'' | 'active' | 'drafts'>(''),
    trash = ref(false)
  const folderId = ref('')
  const workStatus = ref<'' | WorkStatus>('')
  const loading = ref(false),
    error = ref(''),
    pending = ref(false),
    editorOpen = ref(false),
    editingId = ref<string | null>(null)
  let controller: AbortController | undefined
  let correctingPage = false
  const keys = new Map<string, string>()
  async function refresh() {
    if (!alive || !active || !auth.token) return
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = ''
    const requestedPage = page.value
    async function correctPage(count: number) {
      const lastPage = Math.max(1, Math.ceil(count / 30))
      if (requestedPage <= lastPage) return false
      // 页码修正由当前刷新负责，避免页码侦听再发一次请求。
      correctingPage = true
      page.value = lastPage
      correctingPage = false
      rows.value = []; recycled.value = []; total.value = count
      if (count > 0) await refresh()
      return true
    }
    try {
      if (trash.value) {
        const result = await listElementTrash(projectId, requestedPage, current.signal)
        if (!current.signal.aborted) {
          if (await correctPage(result.total)) return
          if (current.signal.aborted) return
          recycled.value = result.rows
          total.value = result.total
        }
      } else {
        const result = await listElements(
          projectId,
          {
            pageNum: requestedPage,
            q: search.value,
            folderId: folderId.value || undefined,
            category: category.value || undefined,
            statusGroup: group.value || undefined,
            workStatus: workStatus.value || undefined,
          },
          current.signal,
        )
        if (!current.signal.aborted) {
          if (await correctPage(result.total)) return
          if (current.signal.aborted) return
          rows.value = result.rows
          total.value = result.total
        }
      }
    } catch (cause) {
      if (!current.signal.aborted) {
        rows.value = []
        recycled.value = []
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
  function open(id: string | null) {
    if (!alive || !active || !auth.token) return
    editingId.value = id
    editorOpen.value = true
  }
  async function restore(item: RecycledElement) {
    const ticket = epoch, viewTicket = interaction, snapshot = { ...item }
    if (!active || !currentSession(ticket) || pending.value || !snapshot.canRestore) return
    pending.value = true
    try {
      await ElMessageBox.confirm(`恢复“${snapshot.name}”到原目录，保留原有修订。`, '恢复元素', {
        confirmButtonText: '恢复',
        cancelButtonText: '取消',
      })
    } catch {
      if (currentSession(ticket)) pending.value = false
      return
    }
    if (!active || !currentSession(ticket) || viewTicket !== interaction) {
      if (currentSession(ticket)) pending.value = false
      return
    }
    error.value = ''
    const identity = `${snapshot.targetId}:${snapshot.revision}`
    const key = keys.get(identity) || crypto.randomUUID()
    keys.set(identity, key)
    try {
      await recycleElement(snapshot.targetId, snapshot.revision, true, key)
      if (!currentSession(ticket)) return
      keys.delete(identity)
      await refresh()
    } catch (cause) {
      if (currentSession(ticket)) error.value = cause instanceof Error ? cause.message : '恢复失败'
    } finally {
      if (currentSession(ticket)) pending.value = false
    }
  }
  watch(page, () => {
    if (!correctingPage) void refresh()
  }, { flush: 'sync' })
  watch(trash, filter)
  void refresh()
  function clear() {
    epoch++; controller?.abort(); keys.clear(); rows.value = []; recycled.value = []
    total.value = 0; loading.value = false; pending.value = false; error.value = ''
    editorOpen.value = false; editingId.value = null
  }
  watch(() => [auth.token, auth.user?.permissions.join('|')], () => { clear(); if (active && auth.token) void refresh() }, { flush: 'sync' })
  function suspend() {
    if (!active) return
    interaction++
    active = false; controller?.abort(); loading.value = false
  }
  function resume() {
    if (active || !mountedActive || !visible()) return
    active = true
    void refresh()
  }
  onDeactivated(() => {
    mountedActive = false; suspend()
    rows.value = []; recycled.value = []; total.value = 0; error.value = ''
  })
  onActivated(() => { mountedActive = true; resume() })
  watch(visible, value => value ? resume() : suspend(), { flush: 'sync' })
  onBeforeUnmount(() => { alive = false; clear() })
  return {
    rows,
    recycled,
    total,
    page,
    search,
    category,
    group,
    folderId,
    workStatus,
    trash,
    loading,
    error,
    pending,
    editorOpen,
    editingId,
    refresh,
    filter,
    open,
    restore,
  }
}
