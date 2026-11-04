import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { listProjectTrash, restoreProjectTrash, type TrashEntry, type TrashKind } from '@/api/projectTrash'
import { useBatchRestore } from './useBatchRestore'

export function useProjectTrash(projectId: string, actions: () => string[], visible: () => boolean, changed: () => void | Promise<void>) {
  const auth = useAuthStore()
  const category = ref<'all' | TrashKind>('all')
  const kinds = computed(() => (['asset', 'element', 'folder'] as TrashKind[]).filter(kind => actions().includes(kind === 'folder' ? 'folder:write' : `${kind}:remove`)))
  const records = reactive<Record<TrashKind, TrashEntry[]>>({ asset: [], element: [], folder: [] })
  const totals = reactive<Record<TrashKind, number>>({ asset: 0, element: 0, folder: 0 })
  const pages = reactive<Record<TrashKind, number>>({ asset: 0, element: 0, folder: 0 })
  const errors = reactive<Record<TrashKind, string>>({ asset: '', element: '', folder: '' })
  const loading = ref(false)
  let controller: AbortController | undefined
  const shownKinds = computed(() => kinds.value.filter(kind => category.value === 'all' || category.value === kind))
  const rows = computed(() => shownKinds.value.flatMap(kind => records[kind]).sort((a, b) => b.deletedTime.localeCompare(a.deletedTime)))
  const total = computed(() => shownKinds.value.reduce((sum, kind) => sum + totals[kind], 0))
  const hasMore = computed(() => shownKinds.value.some(kind => records[kind].length < totals[kind]))
  async function load(append = false) {
    if (!visible() || !auth.token) return
    controller?.abort()
    const request = new AbortController()
    controller = request
    loading.value = true
    const targets = append ? shownKinds.value.filter(kind => records[kind].length < totals[kind] || errors[kind]) : kinds.value
    await Promise.all(targets.map(async kind => {
      errors[kind] = ''
      try {
        // 恢复后重取已加载的页，保留后续页失败项的重试入口；失败时不清空旧列表。
        const lastPage = append ? pages[kind] + 1 : Math.max(1, pages[kind])
        const values: TrashEntry[] = append ? [...records[kind]] : []
        let nextTotal = totals[kind], loadedPage = pages[kind]
        for (let page = append ? pages[kind] + 1 : 1; page <= lastPage; page++) {
          const result = await listProjectTrash(projectId, kind, page, request.signal)
          if (request.signal.aborted) return
          values.push(...result.rows)
          nextTotal = result.total
          loadedPage = page
          if (!result.hasNext && page * 30 >= result.total) break
        }
        records[kind] = [...new Map(values.map(row => [row.id, row])).values()]
        totals[kind] = nextTotal
        pages[kind] = loadedPage
      } catch (cause) {
        if (!request.signal.aborted) errors[kind] = cause instanceof Error ? cause.message : '加载失败，请重试'
      }
    }))
    if (!request.signal.aborted) loading.value = false
  }
  async function refresh() { await load(); await changed() }
  const batch = useBatchRestore(() => rows.value, () => visible() && Boolean(auth.token), refresh, restoreProjectTrash,
    '内容', (): string => rows.value.some(item => item.kind === 'folder' && batch.selected.value.includes(item.id)) ? '文件夹恢复后，已经移到上一级的素材和子文件夹不会自动移回。' : '')
  function restore(item: TrashEntry) {
    if (loading.value || batch.pending.value || !item.canRestore) return
    batch.selected.value = [item.id]
    return batch.restore()
  }
  watch([visible, () => auth.token, () => kinds.value.join(',')], () => {
    controller?.abort()
    for (const kind of ['asset', 'element', 'folder'] as TrashKind[]) { records[kind] = []; pages[kind] = 0; totals[kind] = 0; errors[kind] = '' }
    loading.value = false
    if (visible() && auth.token) void load()
  }, { immediate: true, flush: 'sync' })
  onBeforeUnmount(() => controller?.abort())
  return { category, kinds, shownKinds, rows, total, hasMore, errors, loading, batch, load, refresh, restore }
}
