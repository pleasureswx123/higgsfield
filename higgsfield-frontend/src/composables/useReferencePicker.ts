import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { searchReferences, type ReferenceCandidate } from '@/api/references'
import { useAuthStore } from '@/stores/auth'

export function useReferencePicker(projectId: () => string, disabled: () => boolean) {
  const auth = useAuthStore(), contextRevision = ref(0)
  const open = ref(false),
    q = ref(''),
    kind = ref<'' | 'asset' | 'element'>(''),
    rows = ref<ReferenceCandidate[]>([]),
    page = ref(1),
    total = ref(0),
    loading = ref(false),
    error = ref('')
  let sequence = 0,
    alive = true, active = true,
    controller: AbortController | null = null
  async function load() {
    controller?.abort()
    const ticket = ++sequence
    rows.value = []; total.value = 0; error.value = ''; loading.value = false
    if (!alive || !active || !open.value || !auth.token || disabled()) return
    controller = new AbortController()
    loading.value = true
    error.value = ''
    try {
      const result = await searchReferences(
        { projectId: projectId(), q: q.value, kind: kind.value || undefined, pageNum: page.value, pageSize: 12 },
        controller.signal,
      )
      if (!alive || ticket !== sequence) return
      rows.value = result.rows
      total.value = result.total
    } catch (cause) {
      if (alive && ticket === sequence) {
        rows.value = []
        error.value = cause instanceof Error ? cause.message : '读取素材失败'
      }
    } finally {
      if (alive && ticket === sequence) loading.value = false
    }
  }
  function search() {
    page.value = 1
    load()
  }
  function show(source?: '' | 'asset' | 'element') {
    if (!alive || !active || !auth.token || disabled()) return
    if (source !== undefined) kind.value = source
    open.value = true
    search()
  }
  function close() {
    open.value = false
    sequence++
    controller?.abort()
    loading.value = false
    rows.value = []; total.value = 0; error.value = ''
  }
  watch(() => [projectId(), auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions || []), disabled()], () => {
    close()
    contextRevision.value++
  }, { flush: 'sync' })
  onDeactivated(() => { active = false; close() })
  onActivated(() => { active = true })
  onBeforeUnmount(() => {
    alive = false
    close()
  })
  /** 加入操作只接受当前可见查询返回的同一候选对象。 */
  function canSelect(row: ReferenceCandidate) {
    return alive && active && open.value && !loading.value && !!auth.token && !disabled() &&
      row.projectId === projectId() && rows.value.includes(row)
  }
  return { open, q, kind, rows, page, total, loading, error, load, search, show, close, canSelect, contextRevision }
}
