import {
  computed,
  onActivated,
  onDeactivated,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { ElMessageBox, type FormInstance } from 'element-plus'
import {
  actOnFolder,
  createFolder,
  listFolders,
  listFolderTrash,
  updateFolder,
  readFolder,
  type Folder,
  type FolderColor,
  type FolderFields,
  type FolderSort,
  type RecycleFolder,
} from '@/api/folders'

export function useFolders(projectId: string, visible: () => boolean = () => true) {
  const route = useRoute(),
    router = useRouter()
  const auth = useAuthStore()
  const active = ref(visible())
  let mountedActive = true
  let activityEpoch = 0
  let returnToRoot = false
  let identityEpoch = 0
  const current = (epoch: number) => alive && epoch === identityEpoch
  const rows = ref<Folder[]>([]),
    roots = ref<Folder[]>([]),
    crumbs = ref<Folder[]>([])
  const children = reactive<Record<string, Folder[]>>({}),
    expanded = reactive(new Set<string>())
  const currentId = computed(() => crumbs.value.at(-1)?.id ?? null)
  const loading = ref(false),
    pending = ref(false),
    error = ref(''),
    search = ref('')
  const sort = ref<FolderSort>('nameAsc'),
    page = ref(1),
    total = ref(0),
    trash = ref(false)
  const recycled = ref<RecycleFolder[]>([]),
    dialog = ref(false),
    form = ref<FormInstance>()
  const fields = reactive<FolderFields>({ name: '', description: '', color: 'lime' })
  let editorEpoch = 0,
    editorBaseline = JSON.stringify(fields)
  const saveUncertain = ref(false)
  const transferUncertain = ref(false)
  const saveLocked = computed(() => pending.value || saveUncertain.value || transferUncertain.value)
  let transferIntent:
    | {
        id: string
        mode: 'move' | 'copy'
        data: { revision: string; parentId?: string | null; targetParentId?: string | null }
        key: string
      }
    | undefined
  let saveIntent:
    | {
        id?: string
        revision?: string
        data: FolderFields
        parentId: string | null
        kind: 'media' | 'element'
        destination: boolean
        path: Folder[]
        key: string
      }
    | undefined
  const editing = ref<Folder>(),
    createParent = ref<string | null>(null),
    dialogError = ref('')
  const destinationOpen = ref(false),
    destinationMode = ref<'move' | 'copy'>('move')
  const source = ref<Folder>(),
    destinationCrumbs = ref<Folder[]>([]),
    destinations = ref<Folder[]>([])
  const destinationPage = ref(1),
    destinationHasNext = ref(false),
    destinationLoading = ref(false)
  const destinationId = computed(() => destinationCrumbs.value.at(-1)?.id ?? null)
  const destinationSearch = ref(''),
    destinationSort = ref<FolderSort>('nameAsc')
  const createInDestination = ref(false)
  let createDestinationPath: Folder[] = []
  let destinationQuery = ''
  let sequence = 0,
    alive = true,
    key = '',
    signature = '',
    destinationSequence = 0
  const message = (cause: unknown) => (cause instanceof Error ? cause.message : '操作失败，请重试')
  function writeKey(value: unknown) {
    const next = JSON.stringify(value)
    if (signature !== next) {
      signature = next
      key = crypto.randomUUID()
    }
    return key
  }
  async function load() {
    if (!active.value || !alive || !auth.token) return
    const ticket = ++sequence
    loading.value = true
    error.value = ''
    try {
      if (trash.value) {
        const result = await listFolderTrash(projectId, page.value)
        if (!alive || ticket !== sequence) return
        recycled.value = result.rows
        total.value = result.total
      } else {
        const result = await listFolders(projectId, {
          parentId: currentId.value,
          pageNum: page.value,
          pageSize: 30,
          q: search.value,
          sort: sort.value,
        })
        if (!alive || ticket !== sequence) return
        rows.value = result.rows
        total.value = result.total
      }
    } catch (cause) {
      if (alive && ticket === sequence) error.value = message(cause)
    } finally {
      if (alive && ticket === sequence) loading.value = false
    }
  }
  // 树节点按页加载；列表独立分页，搜索不改变当前目录和面包屑。
  const treeNext = reactive<Record<string, number>>({})
  const treeRequests = new Map<string, AbortController>()
  async function loadTree(parent: string | null = null, append = false) {
    if (!active.value || !alive || !auth.token) return
    const node = parent ?? 'root'
    // 连点加载更多只发送一次；刷新同一节点则取代旧请求。
    if (append && (treeRequests.has(node) || treeNext[node] === 0)) return
    treeRequests.get(node)?.abort()
    const controller = new AbortController()
    treeRequests.set(node, controller)
    const pageNum = append ? treeNext[node] || 1 : 1
    try {
      const result = await listFolders(
        projectId,
        {
          parentId: parent,
          pageNum,
          pageSize: 30,
          sort: sort.value,
        },
        controller.signal,
      )
      if (!alive || controller.signal.aborted) return
      const previous = parent ? (children[parent] ?? []) : roots.value
      const values = [
        ...new Map(
          (append ? [...previous, ...result.rows] : result.rows).map((item) => [item.id, item]),
        ).values(),
      ]
      if (parent) children[parent] = values
      else roots.value = values
      treeNext[node] = result.hasNext ? pageNum + 1 : 0
    } catch (cause) {
      if (alive && !controller.signal.aborted) error.value = message(cause)
    } finally {
      if (treeRequests.get(node) === controller) treeRequests.delete(node)
    }
  }
  async function toggle(folder: Folder) {
    if (expanded.has(folder.id)) expanded.delete(folder.id)
    else {
      expanded.add(folder.id)
      await loadTree(folder.id)
    }
  }
  async function refresh() {
    const identity = identityEpoch
    await load()
    if (!current(identity) || !auth.token) return
    await loadTree()
    for (const id of expanded) {
      if (!current(identity) || !auth.token) return
      await loadTree(id)
    }
  }
  function navigate(path: Folder[]) {
    if (!active.value || !auth.token) return
    void router.push({
      query: { ...route.query, tab: 'folders', folder: path.at(-1)?.id, folderView: undefined },
    })
  }
  function showTrash() {
    void router.push({ query: { ...route.query, tab: 'folders', folderView: 'trash' } })
  }
  let navigationSequence = 0
  const locationKey = () =>
    JSON.stringify([route.query.folder ?? null, route.query.folderView ?? null])
  let loadedLocation = ''
  async function syncLocation(preserveFilters = false) {
    if (!active.value || !alive || !auth.token) return
    const ticket = ++navigationSequence
    sequence++
    const id = typeof route.query.folder === 'string' ? route.query.folder : null
    loading.value = true
    try {
      const result = id ? await readFolder(id) : null
      if (!alive || ticket !== navigationSequence) return
      if (result && result.data.folder.projectId !== projectId)
        throw new Error('目录不属于当前项目')
      crumbs.value = result ? [...result.data.ancestors, result.data.folder] : []
      trash.value = route.query.folderView === 'trash'
      if (!preserveFilters) {
        search.value = ''
        page.value = 1
      }
      loadedLocation = locationKey()
      await load()
    } catch (cause) {
      if (alive && ticket === navigationSequence) {
        rows.value = []
        error.value = message(cause)
        loading.value = false
      }
    }
  }
  watch(
    () => [route.query.folder, route.query.folderView],
    () => void syncLocation(),
  )
  function filter() {
    page.value = 1
    void load()
  }
  function changePage(value: number) {
    page.value = value
    void load()
  }
  function startCreate(parentId: string | null) {
    if (!active.value || !alive || !auth.token || saveLocked.value) return
    editorEpoch++
    createInDestination.value = false
    editing.value = undefined
    createParent.value = parentId
    Object.assign(fields, { name: '', description: '', color: 'lime' as FolderColor })
    editorBaseline = JSON.stringify(fields)
    dialogError.value = ''
    signature = ''
    dialog.value = true
  }
  function startEdit(folder: Folder) {
    if (!active.value || !alive || !auth.token || saveLocked.value) return
    editorEpoch++
    createInDestination.value = false
    editing.value = { ...folder }
    Object.assign(fields, {
      name: folder.name,
      description: folder.description,
      color: folder.color,
    })
    dialogError.value = ''
    editorBaseline = JSON.stringify(fields)
    signature = ''
    dialog.value = true
  }
  async function save() {
    if (!active.value) return
    if (transferUncertain.value) return
    const epoch = identityEpoch
    const editor = editorEpoch
    const activity = activityEpoch
    const before = JSON.stringify([
      editing.value,
      fields,
      createParent.value,
      createInDestination.value,
    ])
    if (pending.value || (!saveIntent && !(await form.value?.validate().catch(() => false)))) return
    if (
      !current(epoch) ||
      !active.value ||
      activity !== activityEpoch ||
      editor !== editorEpoch ||
      !auth.token ||
      !dialog.value ||
      pending.value ||
      before !==
        JSON.stringify([editing.value, fields, createParent.value, createInDestination.value])
    )
      return
    pending.value = true
    const data = { ...fields, name: fields.name.trim() }
    saveIntent ??= {
      id: editing.value?.id,
      revision: editing.value?.revision,
      data,
      parentId: createParent.value,
      kind: createInDestination.value ? source.value?.folderKind || 'media' : 'media',
      destination: createInDestination.value,
      path: createDestinationPath.map((item) => ({ ...item })),
      key: crypto.randomUUID(),
    }
    const request = saveIntent
    saveUncertain.value = true
    dialogError.value = ''
    let createdDestination: Folder | undefined
    try {
      const result = request.id
        ? await updateFolder(
            request.id,
            { ...request.data, revision: request.revision! },
            request.key,
          )
        : await createFolder(
            projectId,
            {
              ...request.data,
              parentId: request.parentId,
              folderKind: request.kind,
            },
            request.key,
          )
      if (!current(epoch)) return
      saveIntent = undefined
      saveUncertain.value = false
      if (request.destination && !request.id) createdDestination = result.data
      crumbs.value = crumbs.value.map((item) => (item.id === result.data.id ? result.data : item))
      if (request.parentId && !request.id) expanded.add(request.parentId)
      dialog.value = false
      await refresh()
    } catch (cause) {
      if (current(epoch)) {
        if (
          cause instanceof ApiError &&
          cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
          (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
        ) {
          saveIntent = undefined
          saveUncertain.value = false
        }
        dialogError.value = message(cause)
      }
    } finally {
      if (current(epoch)) {
        pending.value = false
        if (createdDestination) {
          createInDestination.value = false
          chooseDestination([...request.path, createdDestination])
        }
      }
    }
  }
  async function remove(folder: Folder) {
    const epoch = identityEpoch
    const activity = activityEpoch
    if (!active.value || !alive || !auth.token || saveLocked.value) return
    const snapshot = { ...folder }
    pending.value = true
    try {
      await ElMessageBox.confirm(
        `“${snapshot.name}”将移入回收站，可在30天内恢复。子目录与内容移到父目录。`,
        '删除文件夹',
        { confirmButtonText: '移入回收站', cancelButtonText: '取消' },
      )
    } catch {
      if (current(epoch)) pending.value = false
      return
    }
    if (!current(epoch) || !active.value || activity !== activityEpoch) {
      if (current(epoch)) pending.value = false
      return
    }
    error.value = ''
    try {
      await actOnFolder(
        snapshot.id,
        'delete',
        { revision: snapshot.revision },
        writeKey(['delete', snapshot]),
      )
      if (!current(epoch)) return
      const index = crumbs.value.findIndex((item) => item.id === snapshot.id)
      if (index >= 0) {
        if (active.value) navigate([])
        else returnToRoot = true
      }
      expanded.delete(snapshot.id)
      await refresh()
    } catch (cause) {
      if (current(epoch)) error.value = message(cause)
    } finally {
      if (current(epoch)) pending.value = false
    }
  }
  async function restore(entry: RecycleFolder) {
    if (!active.value || !alive || !auth.token) return
    const epoch = identityEpoch
    if (saveLocked.value) return
    pending.value = true
    error.value = ''
    try {
      await actOnFolder(
        entry.targetId,
        'restore',
        { revision: entry.revision },
        writeKey(['restore', entry]),
      )
      if (current(epoch)) await refresh()
    } catch (cause) {
      if (current(epoch)) error.value = message(cause)
    } finally {
      if (current(epoch)) pending.value = false
    }
  }
  async function loadDestinations(append = false) {
    if (
      !active.value ||
      !alive ||
      !auth.token ||
      saveLocked.value ||
      (append && (destinationLoading.value || !destinationHasNext.value))
    )
      return
    const query = JSON.stringify([
      destinationId.value,
      destinationSearch.value,
      destinationSort.value,
    ])
    if (query !== destinationQuery) append = false
    destinationQuery = query
    const ticket = ++destinationSequence
    destinationLoading.value = true
    dialogError.value = ''
    if (!append) {
      destinationPage.value = 1
      destinations.value = []
      destinationHasNext.value = false
    }
    try {
      const result = await listFolders(projectId, {
        parentId: destinationId.value,
        pageNum: destinationPage.value,
        pageSize: 30,
        q: destinationSearch.value,
        sort: destinationSort.value,
        folderKind: source.value?.folderKind || 'media',
      })
      if (!alive || ticket !== destinationSequence) return
      const values = result.rows.filter((item) => item.id !== source.value?.id)
      destinations.value = [
        ...new Map(
          (append ? [...destinations.value, ...values] : values).map((item) => [item.id, item]),
        ).values(),
      ]
      destinationHasNext.value = result.hasNext
      destinationPage.value++
    } catch (cause) {
      if (alive && ticket === destinationSequence) dialogError.value = message(cause)
    } finally {
      if (alive && ticket === destinationSequence) destinationLoading.value = false
    }
  }
  function chooseDestination(path: Folder[]) {
    if (saveLocked.value) return
    destinationSearch.value = ''
    destinationCrumbs.value = path
    void loadDestinations()
  }
  async function enterDestination(folder: Folder) {
    if (!active.value || saveLocked.value || destinationLoading.value || !auth.token) return
    const ticket = ++destinationSequence
    destinationLoading.value = true
    dialogError.value = ''
    try {
      // 搜索返回项目内平铺结果，必须读取真实祖先，不能拼接到当前路径。
      const result = await readFolder(folder.id)
      if (!alive || ticket !== destinationSequence) return
      const path = [...result.data.ancestors, result.data.folder]
      if (path.some((item) => item.id === source.value?.id)) {
        dialogError.value = '不能选择源目录自身或其子目录。'
        return
      }
      if (
        result.data.folder.projectId !== projectId ||
        result.data.folder.folderKind !== source.value?.folderKind
      ) {
        dialogError.value = '目标目录不属于当前项目或目录类型不一致。'
        return
      }
      chooseDestination(path)
    } catch (cause) {
      if (alive && ticket === destinationSequence) dialogError.value = message(cause)
    } finally {
      if (alive && ticket === destinationSequence) destinationLoading.value = false
    }
  }
  function startDestination(folder: Folder, mode: 'move' | 'copy') {
    if (!active.value || !alive || !auth.token || saveLocked.value) return
    source.value = { ...folder }
    destinationSearch.value = ''
    destinationSort.value = 'nameAsc'
    destinationMode.value = mode
    destinationCrumbs.value = []
    dialogError.value = ''
    signature = ''
    destinationOpen.value = true
    void loadDestinations()
  }
  function startDestinationCreate() {
    if (
      !active.value ||
      !auth.token ||
      saveLocked.value ||
      destinationLoading.value ||
      destinationSearch.value.trim() ||
      !destinationOpen.value
    )
      return
    createDestinationPath = destinationCrumbs.value.map((item) => ({ ...item }))
    startCreate(destinationId.value)
    createInDestination.value = true
  }
  async function transfer() {
    const epoch = identityEpoch
    if (
      !active.value ||
      !alive ||
      !auth.token ||
      !destinationOpen.value ||
      !source.value ||
      pending.value ||
      saveUncertain.value ||
      destinationLoading.value ||
      destinationSearch.value.trim()
    )
      return
    pending.value = true
    dialogError.value = ''
    const item = source.value
    const data = {
      revision: item.revision,
      ...(destinationMode.value === 'move'
        ? { parentId: destinationId.value }
        : { targetParentId: destinationId.value }),
    }
    transferIntent ??= { id: item.id, mode: destinationMode.value, data, key: crypto.randomUUID() }
    const request = transferIntent
    transferUncertain.value = true
    try {
      await actOnFolder(request.id, request.mode, request.data, request.key)
      if (!current(epoch)) return
      transferIntent = undefined
      transferUncertain.value = false
      if (request.mode === 'move' && crumbs.value.some((crumb) => crumb.id === request.id)) {
        if (active.value) navigate([])
        else returnToRoot = true
      }
      destinationOpen.value = false
      await refresh()
    } catch (cause) {
      if (current(epoch)) {
        if (
          cause instanceof ApiError &&
          cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS' &&
          (cause.code === 601 || (cause.code >= 400 && cause.code < 500 && cause.code !== 408))
        ) {
          transferIntent = undefined
          transferUncertain.value = false
        }
        dialogError.value = message(cause)
      }
    } finally {
      if (current(epoch)) pending.value = false
    }
  }
  watch(
    () => [auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions ?? [])],
    () => {
      saveIntent = undefined
      saveUncertain.value = false
      transferIntent = undefined
      transferUncertain.value = false
      returnToRoot = false
      loadedLocation = ''
      identityEpoch++
      sequence++
      navigationSequence++
      destinationSequence++
      for (const controller of treeRequests.values()) controller.abort()
      treeRequests.clear()
      rows.value = []
      roots.value = []
      crumbs.value = []
      recycled.value = []
      destinations.value = []
      expanded.clear()
      for (const id of Object.keys(children)) delete children[id]
      for (const id of Object.keys(treeNext)) delete treeNext[id]
      total.value = 0
      loading.value = false
      destinationLoading.value = false
      pending.value = false
      dialog.value = false
      destinationOpen.value = false
      editing.value = undefined
      source.value = undefined
      Object.assign(fields, { name: '', description: '', color: 'lime' })
      createParent.value = null
      destinationCrumbs.value = []
      destinationSearch.value = ''
      destinationPage.value = 1
      destinationHasNext.value = false
      destinationQuery = ''
      createInDestination.value = false
      createDestinationPath = []
      error.value = ''
      dialogError.value = ''
      key = ''
      signature = ''
      if (active.value && auth.token) {
        void syncLocation()
        void loadTree()
      }
    },
    { flush: 'sync' },
  )
  onMounted(() => {
    void syncLocation()
    void loadTree()
  })
  function suspend() {
    if (!active.value) return
    active.value = false
    activityEpoch++
    sequence++
    navigationSequence++
    destinationSequence++
    for (const controller of treeRequests.values()) controller.abort()
    treeRequests.clear()
    loading.value = false
    destinationLoading.value = false
  }
  function resume() {
    if (!mountedActive || !visible()) return
    if (active.value) return
    active.value = true
    if (returnToRoot) {
      returnToRoot = false
      navigate([])
    } else void syncLocation(loadedLocation === locationKey())
    void loadTree()
    if (destinationOpen.value && !saveLocked.value) void loadDestinations()
  }
  onDeactivated(() => {
    mountedActive = false
    suspend()
  })
  onActivated(() => {
    mountedActive = true
    resume()
  })
  watch(
    visible,
    (value) => {
      if (value) resume()
      else suspend()
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(() => {
    alive = false
    sequence++
    destinationSequence++
    for (const controller of treeRequests.values()) controller.abort()
    treeRequests.clear()
  })
  async function confirmLeave() {
    if (saveLocked.value) return false
    if (!dialog.value || JSON.stringify(fields) === editorBaseline) return true
    const activity = activityEpoch
    const identity = identityEpoch,
      editor = editorEpoch
    try {
      await ElMessageBox.confirm('未保存的目录名称、描述或颜色将被丢弃。', '放弃目录修改', {
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
      })
      return (
        current(identity) &&
        activity === activityEpoch &&
        editor === editorEpoch &&
        !saveLocked.value
      )
    } catch {
      return false
    }
  }
  async function closeEditor() {
    const identity = identityEpoch,
      editor = editorEpoch
    if (!(await confirmLeave()) || !current(identity) || editor !== editorEpoch || saveLocked.value)
      return
    editorEpoch++
    dialog.value = false
  }
  onBeforeRouteLeave(confirmLeave)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || confirmLeave())
  return {
    active,
    rows,
    roots,
    crumbs,
    children,
    expanded,
    currentId,
    loading,
    pending,
    saveLocked,
    saveUncertain,
    transferUncertain,
    error,
    search,
    sort,
    page,
    total,
    trash,
    recycled,
    dialog,
    confirmLeave,
    closeEditor,
    form,
    fields,
    editing,
    dialogError,
    treeNext,
    loadTree,
    toggle,
    refresh,
    navigate,
    showTrash,
    filter,
    changePage,
    startCreate,
    startEdit,
    save,
    remove,
    restore,
    destinationOpen,
    destinationMode,
    destinationCrumbs,
    destinations,
    destinationHasNext,
    destinationLoading,
    destinationSearch,
    destinationSort,
    enterDestination,
    loadDestinations,
    chooseDestination,
    startDestination,
    startDestinationCreate,
    createInDestination,
    transfer,
  }
}
