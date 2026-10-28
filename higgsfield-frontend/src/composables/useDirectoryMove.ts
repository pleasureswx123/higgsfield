import { computed, onActivated, onDeactivated, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessageBox, type FormInstance } from 'element-plus'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import {
  createFolder,
  listFolders,
  readFolder,
  type FolderSort,
  type Folder,
  type FolderColor,
} from '@/api/folders'
import { moveLibraryEntry, copyLibraryEntry } from '@/api/assets'
import { moveElement } from '@/api/elements'

export interface MovableEntry {
  id: string
  name: string
  revision: string
  folderId: string | null
}
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export function useDirectoryMove(
  projectId: string,
  allowed: () => boolean,
  changed: (ids: string[], summary: string) => void,
  kind: 'media' | 'element' = 'media',
  canCreateFolder: () => boolean = () => false,
  visible: () => boolean = () => true,
  operation: 'move' | 'copy' = 'move',
) {
  const auth = useAuthStore(),
    entry = ref<MovableEntry | null>(null),
    path = ref<Folder[]>([]),
    rows = ref<Folder[]>([])
  const loading = ref(false),
    saving = ref(false),
    uncertain = ref(false),
    hasNext = ref(false),
    error = ref('')
  const q = ref(''),
    appliedQuery = ref(''),
    sort = ref<FolderSort>('nameAsc')
  const searching = computed(() => Boolean(appliedQuery.value))
  let mountedActive = true
  const active = ref(visible())
  const entries = ref<MovableEntry[]>([]),
    report = ref('')
  let deferredIds: string[] = [],
    deferredReport = ''
  const creating = ref(false),
    createUncertain = ref(false),
    createOpen = ref(false)
  const createForm = ref<FormInstance>()
  const newFolder = reactive({ name: '', description: '', color: 'lime' as FolderColor })
  const createDirty = computed(
    () =>
      createOpen.value &&
      Boolean(newFolder.name || newFolder.description || newFolder.color !== 'lime'),
  )
  let createInteraction = 0
  let createIntent:
    { data: Parameters<typeof createFolder>[1]; key: string; path: Folder[] } | undefined
  const locked = computed(
      () => saving.value || uncertain.value || creating.value || createUncertain.value,
    ),
    folderId = computed(() => path.value.at(-1)?.id || null)
  let page = 1,
    epoch = 0,
    reader: AbortController | undefined,
    writer: AbortController | undefined
  const intents = new Map<
    string,
    { data: { entryId: string; folderId: string | null; revision: string }; key: string }
  >()
  function clear() {
    createInteraction++
    createIntent = undefined
    creating.value = false
    createUncertain.value = false
    createOpen.value = false
    Object.assign(newFolder, { name: '', description: '', color: 'lime' })
    q.value = ''
    appliedQuery.value = ''
    sort.value = 'nameAsc'
    epoch++
    reader?.abort()
    writer?.abort()
    entry.value = null
    rows.value = []
    path.value = []
    saving.value = false
    loading.value = false
    uncertain.value = false
    hasNext.value = false
    intents.clear()
    entries.value = []
    error.value = ''
  }
  async function load(append = false) {
    if (
      !active.value ||
      !auth.token ||
      !entry.value ||
      !allowed() ||
      (append && (loading.value || !hasNext.value))
    )
      return
    reader?.abort()
    const controller = new AbortController()
    reader = controller
    if (!append) {
      page = 1
      rows.value = []
    }
    loading.value = true
    error.value = ''
    try {
      const result = await listFolders(
        projectId,
        {
          parentId: searching.value ? undefined : folderId.value,
          q: appliedQuery.value,
          sort: sort.value,
          folderKind: kind,
          pageNum: page,
          pageSize: 30,
        },
        controller.signal,
      )
      if (controller.signal.aborted) return
      rows.value = [
        ...new Map(
          (append ? [...rows.value, ...result.rows] : result.rows).map((row) => [row.id, row]),
        ).values(),
      ]
      hasNext.value = result.hasNext
      page++
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '目录读取失败'
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  function openMany(values: MovableEntry[]) {
    if (
      !active.value ||
      !auth.token ||
      locked.value ||
      createOpen.value ||
      !allowed() ||
      !values.length
    )
      return
    clear()
    report.value = ''
    entries.value = [...new Map(values.map((value) => [value.id, { ...value }])).values()]
    entry.value = entries.value[0] || null
    void load()
  }
  function open(value: MovableEntry) {
    openMany([value])
  }
  function navigate(value: Folder[]) {
    if (active.value && auth.token && allowed() && !locked.value) {
      createInteraction++
      path.value = [...value]
      q.value = ''
      appliedQuery.value = ''
      void load()
    }
  }
  function search() {
    if (!active.value || !auth.token || !entry.value || !allowed() || locked.value) return
    appliedQuery.value = q.value.trim()
    void load()
  }
  function changeSort(value: FolderSort) {
    if (!active.value || !auth.token || !allowed() || locked.value) return
    sort.value = value
    void load()
  }
  async function selectFolder(folder: Folder) {
    if (!active.value || !auth.token || !entry.value || !allowed() || locked.value) return
    if (!searching.value) {
      navigate([...path.value, folder])
      return
    }
    reader?.abort()
    const controller = new AbortController()
    reader = controller
    loading.value = true
    error.value = ''
    try {
      const result = await readFolder(folder.id, controller.signal)
      if (controller.signal.aborted || !active.value || !allowed() || locked.value) return
      const { folder: target, ancestors } = result.data
      if (
        target.id !== folder.id ||
        [target, ...ancestors].some(
          (item) => item.projectId !== projectId || item.folderKind !== kind,
        )
      )
        throw new Error('所选目录不属于当前项目或目录类型')
      navigate([...ancestors, target])
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '目标目录读取失败'
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  }
  function close() {
    if (locked.value) return
    if (!createDirty.value) return clear()
    return confirmDiscardCreate().then((accepted) => {
      if (accepted) clear()
    })
  }
  async function confirmDiscardCreate() {
    if (locked.value) return false
    if (!createDirty.value) return true
    const ticket = epoch,
      view = createInteraction
    try {
      await ElMessageBox.confirm(
        '尚未创建的目录配置将被丢弃。已有目录和条目保持不变。',
        '放弃新建目录',
        {
          confirmButtonText: '放弃修改',
          cancelButtonText: '继续编辑',
        },
      )
      return ticket === epoch && view === createInteraction && !locked.value
    } catch {
      return false
    }
  }
  function startCreate() {
    if (
      !active.value ||
      !auth.token ||
      !entry.value ||
      !allowed() ||
      !canCreateFolder() ||
      locked.value ||
      loading.value ||
      searching.value ||
      createOpen.value
    )
      return
    createInteraction++
    Object.assign(newFolder, { name: '', description: '', color: 'lime' })
    createOpen.value = true
    createForm.value?.clearValidate()
  }
  async function cancelCreate() {
    if (await confirmDiscardCreate()) {
      createInteraction++
      createOpen.value = false
    }
  }
  async function submitCreate() {
    if (
      !active.value ||
      !auth.token ||
      !entry.value ||
      !allowed() ||
      !canCreateFolder() ||
      creating.value ||
      saving.value ||
      uncertain.value ||
      !createOpen.value
    )
      return
    const ticket = epoch,
      view = createInteraction,
      before = JSON.stringify([newFolder, folderId.value])
    if (!createIntent && !(await createForm.value?.validate().catch(() => false))) return
    if (
      ticket !== epoch ||
      view !== createInteraction ||
      !active.value ||
      !auth.token ||
      !allowed() ||
      !canCreateFolder() ||
      !createOpen.value ||
      creating.value ||
      saving.value ||
      uncertain.value ||
      before !== JSON.stringify([newFolder, folderId.value])
    )
      return
    createIntent ??= {
      data: {
        ...newFolder,
        name: newFolder.name.trim(),
        parentId: folderId.value,
        folderKind: kind,
      },
      key: crypto.randomUUID(),
      path: [...path.value],
    }
    const request = createIntent
    creating.value = true
    createUncertain.value = true
    error.value = ''
    try {
      const response = await createFolder(projectId, request.data, request.key)
      if (ticket !== epoch) return
      createIntent = undefined
      createUncertain.value = false
      createOpen.value = false
      path.value = [...request.path, response.data]
      q.value = ''
      appliedQuery.value = ''
      report.value = `已创建目录“${response.data.name}”，请确认是否移动到此目录。`
      await load()
    } catch (cause) {
      if (ticket !== epoch) return
      if (
        cause instanceof ApiError &&
        cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
        (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
      ) {
        createIntent = undefined
        createUncertain.value = false
      }
      error.value = cause instanceof Error ? cause.message : '目录创建失败'
    } finally {
      if (ticket === epoch) creating.value = false
    }
  }
  async function save() {
    if (
      !active.value ||
      !auth.token ||
      !entry.value ||
      !allowed() ||
      saving.value ||
      createOpen.value ||
      creating.value ||
      createUncertain.value ||
      loading.value ||
      searching.value
    )
      return
    const sameFolder = entries.value.filter(
      (item) => operation !== 'copy' && !intents.has(item.id) && item.folderId === folderId.value,
    )
    if (sameFolder.length === entries.value.length) {
      error.value = '所选条目已在此目录。'
      return
    }
    // 首次提交时冻结整批目标与修订，后续仅重试尚未成功的原请求。
    const items = entries.value.filter((item) => !sameFolder.some((same) => same.id === item.id))
    for (const item of items) {
      if (!intents.has(item.id))
        intents.set(item.id, {
          data: { entryId: item.id, folderId: folderId.value, revision: item.revision },
          key: crypto.randomUUID(),
        })
    }
    entries.value = items
    const current = epoch,
      moved: string[] = [],
      failures: string[] = []
    saving.value = true
    uncertain.value = true
    error.value = ''
    try {
      for (const item of items) {
        if (current !== epoch || !active.value || !allowed() || !auth.token) break
        const intent = intents.get(item.id)!
        writer = new AbortController()
        try {
          if (kind === 'element') {
            const { entryId, folderId, revision } = intent.data
            await moveElement(entryId, { folderId, revision }, intent.key, writer.signal)
          } else await (operation === 'copy' ? copyLibraryEntry : moveLibraryEntry)(projectId, intent.data, intent.key, writer.signal)
          if (current !== epoch) return
          intents.delete(item.id)
          moved.push(item.id)
          entries.value = entries.value.filter((value) => value.id !== item.id)
        } catch (cause) {
          if (current !== epoch) return
          const definitive =
            cause instanceof ApiError &&
            ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') ||
              (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
          if (definitive) intents.delete(item.id)
          failures.push(`${item.name}：${cause instanceof Error ? cause.message : '移动失败'}`)
        }
      }
      if (current !== epoch) return
      const remaining = items.length - moved.length - failures.length
      report.value = `本次已${operation === 'copy' ? '复制' : '移动'} ${moved.length} 项。${sameFolder.length ? `${sameFolder.length} 项已在目标目录，未重复移动。` : ''}${remaining ? `${remaining} 项尚未执行。` : ''}`
      uncertain.value = intents.size > 0
      error.value =
        failures.join('；') +
        (uncertain.value
          ? '；部分结果尚未确认或尚未执行，请重试同一批请求。'
          : failures.length
            ? '；请关闭后刷新列表，再重新选择失败项。'
            : '')
      if (!entries.value.length) clear()
      else entry.value = entries.value[0] || null
      if (moved.length) {
        if (active.value) changed(moved, report.value)
        else {
          deferredIds.push(...moved)
          deferredReport = report.value
        }
      }
    } finally {
      if (current === epoch) saving.value = false
    }
  }
  watch(
    () => auth.token,
    () => {
      deferredIds = []
      deferredReport = ''
      clear()
    },
    { flush: 'sync' },
  )
  watch(
    allowed,
    (value) => {
      if (!value) {
        reader?.abort()
        rows.value = []
        loading.value = false
        hasNext.value = false
      } else if (active.value && entry.value && !locked.value) {
        void load()
      }
    },
    { flush: 'sync' },
  )
  // 撤权后无法继续确认，允许离开；同一账号的未确认意图仍保留原键。
  const canLeave = () => {
    if (!active.value || !auth.token || !allowed()) return true
    if (locked.value) return false
    return createDirty.value ? confirmDiscardCreate() : true
  }
  onBeforeRouteLeave(canLeave)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || canLeave())
  function suspend() {
    if (!active.value) return
    createInteraction++
    active.value = false
    reader?.abort()
    loading.value = false
    rows.value = []
    hasNext.value = false
    // 已发出的写请求继续确认结果；保留原幂等意图，禁止后台发起新操作。
  }
  function resume() {
    if (active.value || !mountedActive || !visible()) return
    active.value = true
    if (deferredIds.length) {
      const ids = deferredIds
      deferredIds = []
      changed(ids, deferredReport)
      deferredReport = ''
    }
    if (entry.value && !locked.value) void load()
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
    active.value = false
    deferredIds = []
    deferredReport = ''
    clear()
  })
  return {
    q,
    createOpen,
    createForm,
    newFolder,
    creating,
    createUncertain,
    startCreate,
    cancelCreate,
    submitCreate,
    sort,
    searching,
    search,
    changeSort,
    selectFolder,
    active,
    entry,
    entries,
    report,
    path,
    rows,
    loading,
    saving,
    uncertain,
    hasNext,
    error,
    locked,
    open,
    openMany,
    navigate,
    close,
    load,
    save,
  }
}
