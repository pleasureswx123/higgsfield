import { ref, watch, onBeforeUnmount } from 'vue'
import { createFolder, listFolders, readFolder, type Folder } from '@/api/folders'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

/** 选择或新建产出目录，不移动已有素材。 */
export function useCreationDestination(projectId: string, selected: () => string | null, canCreate: () => boolean) {
  const auth = useAuthStore()
  const open = ref(false), label = ref('全部素材 · 根目录'), error = ref(''), loading = ref(false)
  const path = ref<Folder[]>([]), rows = ref<Folder[]>([]), page = ref(1), hasNext = ref(false)
  const generationBlock = ref('正在检查保存位置')
  const emptyProject = ref(false), creating = ref(false), createError = ref(''), uncertain = ref(false)
  let intent: { name: string; parentId: string | null; key: string } | undefined
  let lifetime = 0
  let sequence = 0, request: AbortController | undefined
  watch([selected, () => auth.token], async ([id], _, cleanup) => {
    const controller = new AbortController()
    cleanup(() => controller.abort())
    generationBlock.value = '正在检查保存位置'
    label.value = id ? '读取保存位置…' : '全部素材 · 根目录'
    if (!auth.token) return
    if (!id) {
      try {
        const result = await listFolders(projectId, { parentId: null, folderKind: 'media', pageSize: 1 }, controller.signal)
        if (!controller.signal.aborted) {
          emptyProject.value = result.total === 0
          generationBlock.value = emptyProject.value ? '请先创建文件夹' : ''
        }
      } catch { if (!controller.signal.aborted) { emptyProject.value = false; generationBlock.value = '保存位置读取失败，请重新选择' } }
      return
    }
    emptyProject.value = false
    try {
      const result = await readFolder(id, controller.signal)
      if (!controller.signal.aborted) { label.value = [...result.data.ancestors, result.data.folder].map(item => item.name).join(' / '); generationBlock.value = '' }
    } catch { if (!controller.signal.aborted) { label.value = '保存位置暂不可用，请重新选择'; generationBlock.value = label.value } }
  }, { immediate: true })
  async function load() {
    const ticket = ++sequence
    request?.abort(); request = new AbortController()
    loading.value = true; error.value = ''
    try {
      const result = await listFolders(projectId, { parentId: path.value.at(-1)?.id ?? null, folderKind: 'media', pageNum: page.value, pageSize: 30, sort: 'nameAsc' }, request.signal)
      if (ticket !== sequence) return
      rows.value = result.rows; hasNext.value = result.hasNext
    } catch (cause) { if (ticket === sequence) error.value = cause instanceof Error ? cause.message : '目录读取失败' }
    finally { if (ticket === sequence) loading.value = false }
  }
  async function create(name: string): Promise<Folder | undefined> {
    if (creating.value || !auth.token || !canCreate() || !name.trim()) return
    intent ??= { name: name.trim(), parentId: path.value.at(-1)?.id ?? null, key: crypto.randomUUID() }
    const token = auth.token, epoch = lifetime
    creating.value = true; createError.value = ''; uncertain.value = true
    try {
      const result = await createFolder(projectId, { name: intent.name, parentId: intent.parentId, folderKind: 'media', description: '', color: 'lime' }, intent.key)
      if (token !== auth.token || epoch !== lifetime) return
      intent = undefined; uncertain.value = false; emptyProject.value = false
      return result.data
    } catch (cause) {
      if (token !== auth.token || epoch !== lifetime) return
      if (cause instanceof ApiError && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' && (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))) { intent = undefined; uncertain.value = false }
      createError.value = cause instanceof Error ? cause.message : '创建失败，请重试'
    } finally { if (epoch === lifetime) creating.value = false }
  }
  function navigate(next: Folder[]) { path.value = next; page.value = 1; rows.value = []; void load() }
  function start() { open.value = true; navigate([]) }
  function stop() { lifetime++; creating.value = false; sequence++; request?.abort(); open.value = false; rows.value = []; loading.value = false }
  watch(() => auth.token, () => { stop(); intent = undefined; uncertain.value = false })
  onBeforeUnmount(stop)
  return { generationBlock, emptyProject, creating, createError, uncertain, create, open, label, path, rows, page, hasNext, loading, error, load, navigate, start }
}
