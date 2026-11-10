import { onBeforeUnmount, ref } from 'vue'
import type { LoadFunction } from 'element-plus/es/components/tree/src/tree.type'
import { listFolders, readFolder, type Folder, type FolderKind, type FolderSort } from '@/api/folders'

export interface DestinationNode {
  id: string
  name: string
  path: Folder[]
  leaf: boolean
  disabled: boolean
  children?: DestinationNode[]
}

export function useDestinationTree(projectId: string, kind: FolderKind, excluded: () => string | undefined, locked: () => boolean, select: (path: Folder[]) => void) {
  const query = ref(''), sort = ref<FolderSort>('nameAsc'), searching = ref(false), busy = ref(false), error = ref('')
  const results = ref<DestinationNode[]>([]), treeKey = ref(0)
  const expanded = ref(['root'])
  const controllers = new Set<AbortController>()
  let sequence = 0, alive = true
  const node = (path: Folder[]): DestinationNode => ({ id: path.at(-1)?.id || 'root', name: path.at(-1)?.name || '项目根目录', path,
    leaf: path.some(item => item.id === excluded()) || (path.length > 0 && !path.at(-1)!.hasChildren), disabled: path.some(item => item.id === excluded()) })
  async function pages(parentId: string | null | undefined, q: string, signal: AbortSignal) {
    const rows: Folder[] = []
    for (let pageNum = 1; ; pageNum++) {
      const response = await listFolders(projectId, { parentId, q, sort: sort.value, folderKind: kind, pageNum, pageSize: 100 }, signal)
      rows.push(...response.rows)
      if (!response.hasNext) return rows
      if (!response.rows.length) throw new Error('目录分页返回异常，请重新加载')
    }
  }
  const load: LoadFunction = async (parent, resolve, reject) => {
    if (!parent.level) { resolve([node([])]); return }
    const controller = new AbortController(); controllers.add(controller)
    try {
      const rows = await pages(parent.data.id === 'root' ? null : parent.data.id, '', controller.signal)
      if (alive && !controller.signal.aborted) resolve(rows.map(folder => node([...parent.data.path, folder])))
    } catch (cause) {
      if (alive && !controller.signal.aborted) { error.value = cause instanceof Error ? cause.message : '目录加载失败'; reject() }
    } finally { controllers.delete(controller) }
  }
  async function search() {
    if (locked()) return
    const ticket = ++sequence, term = query.value.trim()
    busy.value = true; error.value = ''
    const controller = new AbortController(); controllers.add(controller)
    try {
      if (!term) { searching.value = false; return }
      const matches = await pages(undefined, term, controller.signal)
      const root = node([]); root.children = []
      for (const match of matches) {
        const response = await readFolder(match.id, controller.signal)
        const path = [...response.data.ancestors, response.data.folder]
        if (path.some(item => item.projectId !== projectId || item.folderKind !== kind)) continue
        let parent = root
        for (let index = 0; index < path.length; index++) {
          parent.children ??= []
          let child = parent.children.find(item => item.id === path[index]!.id)
          if (!child) { child = node(path.slice(0, index + 1)); child.children = []; parent.children.push(child) }
          parent = child
        }
      }
      if (alive && ticket === sequence) { results.value = matches.length ? [root] : []; searching.value = true }
    } catch (cause) { if (alive && ticket === sequence) error.value = cause instanceof Error ? cause.message : '搜索失败' }
    finally { controllers.delete(controller); if (alive && ticket === sequence) busy.value = false }
  }
  async function choose(value: DestinationNode) {
    if (locked() || busy.value || value.disabled) return
    const ticket = ++sequence
    busy.value = true; error.value = ''
    const controller = new AbortController(); controllers.add(controller)
    try {
      const response = value.id === 'root' ? null : await readFolder(value.id, controller.signal)
      const path = response ? [...response.data.ancestors, response.data.folder] : []
      if (path.some(item => item.projectId !== projectId || item.folderKind !== kind || item.id === excluded())) throw new Error('不能选择此目标目录')
      if (alive && ticket === sequence && !locked()) select(path)
    } catch (cause) { if (alive && ticket === sequence) error.value = cause instanceof Error ? cause.message : '目标目录读取失败' }
    finally { controllers.delete(controller); if (alive && ticket === sequence) busy.value = false }
  }
  async function reload() {
    if (locked() || busy.value) return
    error.value = ''
    // 首次搜索失败时尚未进入搜索视图，仍需按原关键词重试。
    if (query.value.trim() || searching.value) await search()
    else treeKey.value++
  }
  function reveal(path: Folder[]) {
    // 新建目录或选择搜索结果时，重新读取真实分支，不能沿用空目录的叶节点缓存。
    sequence++
    controllers.forEach(controller => controller.abort())
    query.value = ''; searching.value = false; busy.value = false; error.value = ''
    expanded.value = ['root', ...path.map(folder => folder.id)]
    treeKey.value++
  }
  onBeforeUnmount(() => { alive = false; sequence++; controllers.forEach(controller => controller.abort()) })
  return { query, sort, searching, busy, error, results, treeKey, load, search, choose, reload, reveal, expanded }
}
