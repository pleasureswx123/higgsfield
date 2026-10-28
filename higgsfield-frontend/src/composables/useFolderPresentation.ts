import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { Folder } from '@/api/folders'
import type { FolderViewSettings } from '@/api/viewPreferences'

export function useFolderPresentation(expanded: Set<string>, loadTree: (id: string) => Promise<void>) {
  const pinned = ref<string[]>([]), order = ref<string[]>([]), notice = ref('')
  let epoch = 0
  const settings = computed<FolderViewSettings>(() => ({ expandedFolderIds: [...expanded], pinnedFolderIds: [...pinned.value], folderOrderIds: [...order.value] }))
  function arrange(rows: Folder[]) {
    const positions = new Map(order.value.map((id, index) => [id, index]))
    return [...rows].sort((a, b) => Number(pinned.value.includes(b.id)) - Number(pinned.value.includes(a.id)) ||
      (positions.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (positions.get(b.id) ?? Number.MAX_SAFE_INTEGER))
  }
  function pin(id: string) {
    notice.value = ''
    if (pinned.value.includes(id)) pinned.value = pinned.value.filter(value => value !== id)
    else if (pinned.value.length < 500) pinned.value = [...pinned.value, id]
    else notice.value = '最多保存500个置顶目录，请先取消部分置顶。'
  }
  function moveUp(rows: Folder[], id: string) {
    const siblings = arrange(rows), index = siblings.findIndex(row => row.id === id)
    if (index <= 0) return
    const previous = siblings[index - 1]!
    if (pinned.value.includes(previous.id) !== pinned.value.includes(id)) {
      notice.value = '置顶目录优先显示，请先调整置顶状态。'; return
    }
    const ids = siblings.map(row => row.id)
    ;[ids[index - 1], ids[index]] = [ids[index]!, ids[index - 1]!]
    const remaining = order.value.filter(value => !ids.includes(value))
    if (ids.length + remaining.length > 500) { notice.value = '最多保存500个目录的个人顺序。'; return }
    order.value = [...remaining, ...ids]; notice.value = ''
  }
  async function restore(value: FolderViewSettings) {
    const current = ++epoch
    pinned.value = [...(value.pinnedFolderIds || [])]; order.value = [...(value.folderOrderIds || [])]
    expanded.clear()
    for (const id of value.expandedFolderIds || []) expanded.add(id)
    for (const id of value.expandedFolderIds || []) {
      if (current !== epoch) return
      await loadTree(id)
    }
  }
  watch(() => useAuthStore().token, () => {
    epoch++; pinned.value = []; order.value = []; expanded.clear(); notice.value = ''
  })
  onBeforeUnmount(() => { epoch++ })
  return { pinned, settings, notice, arrange, pin, moveUp, restore }
}
