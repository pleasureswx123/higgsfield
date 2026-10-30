import { computed, ref, watch, onBeforeUnmount, type Ref } from 'vue'
import { listElements, readElement, type ElementRecord } from '@/api/elements'
import { readMembers } from '@/api/projectWorkspace'
import { listFolders, createFolder, type Folder } from '@/api/folders'

export function useElementLibrary(projectId: string, rows: Ref<ElementRecord[]>, visible: () => boolean, query: () => Omit<Parameters<typeof listElements>[1], 'pageNum'>) {
  const displayRows = ref<ElementRecord[]>([])
  const memberNames = ref<Record<string, string>>({})
  const renderedRows = computed(() => displayRows.value.map(row => ({ ...row, performerName: row.performerId ? memberNames.value[row.performerId] : undefined })))
  const folders = ref<(Folder & { depth: number })[]>([])
  const error = ref(''), exporting = ref(false), creating = ref(false)
  let controller: AbortController | undefined
  let folderController: AbortController | undefined
  const exportController = new AbortController()
  watch([rows, visible], async () => {
    controller?.abort()
    displayRows.value = rows.value
    if (!visible()) return
    const current = controller = new AbortController()
    // 按当前页读取固定版本媒体，避免预览播放时间引发重复加载。
    const enriched = [...rows.value]
    for (let start = 0; start < enriched.length; start += 4) {
      await Promise.all(enriched.slice(start, start + 4).map(async (row, offset) => {
        try {
          const result = await readElement(row.id, current.signal)
          enriched[start + offset] = { ...row, media: result.data.currentRevision.media }
        } catch { /* 列表仍可使用，详情加载失败不阻断其他元素 */ }
      }))
      if (current.signal.aborted) return
      displayRows.value = [...enriched]
    }
  }, { immediate: true })
  async function loadFolders() {
    folderController?.abort()
    const current = folderController = new AbortController()
    const result: (Folder & { depth: number })[] = []
    async function load(parentId: string | null, depth: number) {
      for (let pageNum = 1; ; pageNum++) {
        const page = await listFolders(projectId, { parentId, pageNum, pageSize: 100, folderKind: 'element' }, current.signal)
        for (const folder of page.rows) {
          result.push({ ...folder, depth })
          if (folder.hasChildren) await load(folder.id, depth + 1)
        }
        if (!page.hasNext) break
      }
    }
    try {
      try {
        const names: Record<string, string> = {}
        for (let pageNum = 1; ; pageNum++) {
          const page = await readMembers(projectId, pageNum, 'active', current.signal)
          for (const member of page.rows) names[member.userId] = member.displayName
          if (pageNum * 20 >= page.total || !page.rows.length) break
        }
        if (!current.signal.aborted) memberNames.value = names
      } catch { /* 成员读取失败不阻断文件夹展示。 */ }
      await load(null, 0); if (!current.signal.aborted) folders.value = result }
    catch (e) { if (!current.signal.aborted) error.value = e instanceof Error ? e.message : '文件夹读取失败' }
  }
  watch(visible, active => { if (active) void loadFolders(); else folderController?.abort() }, { immediate: true })
  async function addFolder(name: string) {
    if (creating.value) return
    creating.value = true; error.value = ''
    try { await createFolder(projectId, { name, description: '', color: 'lime', parentId: null, folderKind: 'element' }, crypto.randomUUID()); await loadFolders() }
    catch (e) { error.value = e instanceof Error ? e.message : '创建文件夹失败' }
    finally { creating.value = false }
  }
  async function exportCsv() {
    if (exporting.value) return
    exporting.value = true; error.value = ''
    const params = { ...query() }
    try {
      const all: ElementRecord[] = []
      for (let pageNum = 1; ; pageNum++) {
        const page = await listElements(projectId, { ...params, pageNum, pageSize: 100 }, exportController.signal)
        all.push(...page.rows)
        if (!page.hasNext) break
      }
      const cell = (value: unknown) => {
        let text = String(value ?? '')
        if (/^[=+@\-\t\r]/.test(text)) text = "'" + text
        return '"' + text.replaceAll('"', '""') + '"'
      }
      const categories = { character: '角色', scene: '场景', prop: '道具', other: '其他' }
      const csv = [['名称', '分类', '元素 ID', '描述', '版本', '负责人 ID', '状态'], ...all.map(row => [row.name, categories[row.category], row.alias, row.description, row.label, row.performerId, row.workStatus])].map(row => row.map(cell).join(',')).join('\r\n')
      const url = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a'); link.href = url; link.download = '项目元素.csv'; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { if (!exportController.signal.aborted) error.value = e instanceof Error ? e.message : '导出失败' }
    finally { exporting.value = false }
  }
  onBeforeUnmount(() => { controller?.abort(); folderController?.abort(); exportController.abort() })
  return { displayRows: renderedRows, folders, error, exporting, creating, addFolder, exportCsv }
}
