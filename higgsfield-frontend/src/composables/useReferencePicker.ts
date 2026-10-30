import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { searchReferences, type ReferenceCandidate } from '@/api/references'
import { useAuthStore } from '@/stores/auth'
import { listElements, readElement } from '@/api/elements'

export function useReferencePicker(projectId: () => string, disabled: () => boolean, folderId: () => string | null = () => null) {
  const auth = useAuthStore(), contextRevision = ref(0)
  const open = ref(false),
    q = ref(''),
    kind = ref<'' | 'asset' | 'element'>(''),
    rows = ref<ReferenceCandidate[]>([]),
    page = ref(1),
    total = ref(0),
    loading = ref(false),
    error = ref('')
  const mediaType = ref<'' | 'image' | 'video'>('')
  const category = ref<'' | 'character' | 'scene' | 'prop' | 'other'>('')
  const source = ref<'' | 'uploaded' | 'generated'>('')
  const recent = ref(false)
  const elementScope = ref<'project' | 'mine' | 'folder'>('project')
  const sort = ref<'newest' | 'oldest' | 'name'>('newest')
  let sequence = 0,
    alive = true, active = true,
    controller: AbortController | null = null
  async function load() {
    controller?.abort()
    const ticket = ++sequence
    rows.value = []; total.value = 0; error.value = ''; loading.value = false
    if (!alive || !active || !open.value || !auth.token || disabled()) return
    controller = new AbortController()
    const signal = controller.signal
    loading.value = true
    error.value = ''
    try {
      if (kind.value === 'element' && elementScope.value === 'mine') {
        const result = await listElements(undefined, { scope: 'mine', mineFilter: 'created', q: q.value, category: category.value || undefined, pageNum: page.value, pageSize: 12 }, signal)
        const candidates = await Promise.all(result.rows.map(async item => {
          const detail = await readElement(item.id, signal)
          const media = detail.data.currentRevision.media
          let available: ReferenceCandidate | undefined
          try {
            const result = await searchReferences({ projectId: item.projectId, kind: 'element', elementId: item.id, includeEmptyElements: true, q: '', pageNum: 1, pageSize: 1 }, signal)
            available = result.rows[0]
          } catch { /* 无来源引用权限时仍展示元素，但不允许选择。 */ }
          return { kind: 'element' as const, id: item.id, projectId: item.projectId, displayName: item.name, alias: item.alias, category: item.category,
            elementRevisionId: detail.data.currentRevision.id, assetVersionIds: media.map(value => value.assetVersionId),
            primaryAssetVersionId: media.find(value => value.isPrimary)?.assetVersionId,
            allowedMediaRoles: available?.allowedMediaRoles || [], byteSize: available?.byteSize }
        }))
        if (!alive || ticket !== sequence) return
        rows.value = candidates; total.value = result.total
        return
      }
      const result = await searchReferences(
        { projectId: projectId(), q: q.value, kind: kind.value || undefined, pageNum: page.value, pageSize: 12, mediaType: mediaType.value || undefined, category: kind.value === 'element' ? category.value || undefined : undefined, source: kind.value === 'element' ? undefined : source.value || undefined, recent: recent.value, sort: sort.value, includeEmptyElements: kind.value === 'element', elementScope: elementScope.value === 'folder' ? 'folder' : 'project', folderId: elementScope.value === 'folder' ? folderId() || undefined : undefined },
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
      (row.projectId === projectId() || (kind.value === 'element' && elementScope.value === 'mine')) && rows.value.includes(row)
  }
  return { elementScope, mediaType, category, source, recent, sort, open, q, kind, rows, page, total, loading, error, load, search, show, close, canSelect, contextRevision }
}
