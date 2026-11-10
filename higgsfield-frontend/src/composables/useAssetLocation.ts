import { computed, ref, watch } from 'vue'
import { readFolder, type Folder } from '@/api/folders'

/** 使用素材条目的实际目录，不使用当前浏览目录。 */
export function useAssetLocation(folderId: () => string | null | undefined) {
  const path = ref<Folder[]>([])
  const ready = ref(false)
  watch(folderId, async (id, _, onCleanup) => {
    const controller = new AbortController()
    onCleanup(() => controller.abort())
    path.value = []
    ready.value = id === null
    if (!id) return
    try {
      const { data } = await readFolder(id, controller.signal)
      if (!controller.signal.aborted) {
        path.value = [...data.ancestors.filter(folder => folder.id !== data.folder.id), data.folder]
        ready.value = true
      }
    } catch { /* 不可访问时不提供错误的目录入口。 */ }
  }, { immediate: true })
  const name = computed(() => path.value.at(-1)?.name || '项目根目录')
  const parentPath = computed(() => ['项目根目录', ...path.value.slice(0, -1).map(folder => folder.name)])
  const parentLabel = computed(() => parentPath.value.length > 3
    ? `${parentPath.value[0]} / … / ${parentPath.value.slice(-2).join(' / ')}`
    : parentPath.value.join(' / '))
  return { ready, path, name, parentPath, parentLabel }
}
