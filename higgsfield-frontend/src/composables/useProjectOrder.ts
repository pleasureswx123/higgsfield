import { ref, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { Project } from '@/api/projects'
import { putProjectOrder } from '@/api/projectPreferences'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useProjectUpdatesStore } from '@/stores/projectUpdates'

/** 拖动只改变本人顺序，置顶区和普通区分别排序。 */
export function useProjectOrder(projects: Ref<Project[]>) {
  const auth = useAuthStore(), updates = useProjectUpdatesStore()
  const dragging = ref(''), over = ref(''), saving = ref(false), error = ref('')
  let controller: AbortController | undefined
  let intent: { items: { projectId: string; revision: string }[]; key: string } | undefined
  async function save() {
    if (!intent || saving.value) return
    saving.value = true; error.value = ''; updates.orderLocked = true
    controller = new AbortController()
    const signal = controller.signal
    try {
      await putProjectOrder(intent.items, intent.key, signal)
      if (signal.aborted) return
      intent = undefined; updates.orderLocked = false; updates.notify()
    } catch (cause) {
      if (signal.aborted) return
      error.value = cause instanceof Error ? cause.message : '排序保存失败，请重试'
      if (cause instanceof ApiError && ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause.code >= 400 && cause.code < 500))) {
        intent = undefined; updates.orderLocked = false; updates.notify()
      }
      ElMessage.error(error.value)
    } finally { if (!signal.aborted) saving.value = false }
  }
  function move(source: string, target: string, after = false) {
    if (updates.orderLocked || source === target) return
    const rows = [...projects.value]
    const from = rows.findIndex(row => row.id === source), to = rows.findIndex(row => row.id === target)
    if (from < 0 || to < 0) return
    if (Boolean(rows[from].preference?.isPinned) !== Boolean(rows[to].preference?.isPinned)) {
      ElMessage.info('置顶项目保持在前方，请在相同置顶状态的项目之间排序。'); return
    }
    const [item] = rows.splice(from, 1)
    rows.splice(rows.findIndex(row => row.id === target) + (after ? 1 : 0), 0, item)
    if (rows.every((row, index) => row.id === projects.value[index].id)) return
    intent = { key: crypto.randomUUID(), items: rows.map(row => ({ projectId: row.id, revision: row.preference?.revision || '0' })) }
    void save()
  }
  function start(event: DragEvent, id: string) {
    if (updates.orderLocked || projects.value.length < 2) { event.preventDefault(); return }
    dragging.value = id
    event.dataTransfer?.setData('text/plain', id)
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
  }
  function end() { dragging.value = ''; over.value = '' }
  function drop(event: DragEvent, id: string) {
    const source = dragging.value
    const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect()
    end()
    if (source) move(source, id, event.clientY > bounds.top + bounds.height / 2)
  }
  function keyboard(id: string, direction: number) {
    const index = projects.value.findIndex(row => row.id === id)
    const target = projects.value[index + direction]
    if (target) move(id, target.id, direction > 0)
  }
  function clear() {
    controller?.abort(); intent = undefined; updates.orderLocked = false; saving.value = false; error.value = ''; end()
  }
  watch(() => [auth.token, auth.user?.user.userId], clear, { flush: 'sync' })
  onBeforeUnmount(clear)
  return { dragging, over, saving, error, start, end, drop, keyboard, save, locked: updates }
}
