import { ref, watch, onBeforeUnmount } from 'vue'
import type { LibraryEntry } from '@/api/assets'

/** 生成完成后只强调本次刷新新增的素材；切目录、筛选及离开组件时取消。 */
export function useAssetArrivalHighlights(rows: () => LibraryEntry[], context: () => string, refresh: () => Promise<void>, ready: () => boolean = () => true) {
  const highlighted = ref<string[]>([])
  let timer: ReturnType<typeof setTimeout> | undefined, revision = 0
  function clear() { revision++; clearTimeout(timer); highlighted.value = [] }
  async function refreshGenerated() {
    const current = ++revision, scope = context(), before = new Set(rows().map(row => row.asset.id)), canHighlight = ready()
    await refresh()
    if (current !== revision || scope !== context() || !canHighlight || !ready()) return
    highlighted.value = rows().filter(row => !before.has(row.asset.id)).map(row => row.asset.id)
    clearTimeout(timer)
    if (highlighted.value.length) timer = setTimeout(() => { highlighted.value = [] }, 8000)
  }
  watch(context, clear, { flush: 'sync' })
  onBeforeUnmount(clear)
  return { highlighted, refreshGenerated }
}
