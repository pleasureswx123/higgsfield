import { ref, watch, onBeforeUnmount } from 'vue'
import { readAssetVersion } from '@/api/assets'
import { useAuthStore } from '@/stores/auth'
import { checkReferenceUpdates } from '@/api/references'

/** 只读取当前选中版本的名称，不将展示名称混入生成请求或跨账号缓存。 */
export function useReferenceName(version: () => string, elementRevision: () => string = () => '', project: () => string = () => '') {
  const name = ref(''), auth = useAuthStore()
  let controller: AbortController | undefined
  // 分别比较值，避免草稿输入替换引用对象时，新数组被误判为名称来源发生变化。
  watch([version, elementRevision, project, () => auth.token, () => JSON.stringify(auth.user?.permissions || [])], async () => {
    controller?.abort(); name.value = ''
    if (!version() || !auth.token) return
    const reader = new AbortController(); controller = reader
    try {
      if (elementRevision()) {
        if (!project()) return
        const revision = elementRevision()
        const response = await checkReferenceUpdates(project(), [revision], reader.signal)
        if (!reader.signal.aborted) name.value = response.data.items.find(item => item.elementRevisionId === revision)?.displayName || ''
        return
      }
      const response = await readAssetVersion(version(), reader.signal)
      if (!reader.signal.aborted) name.value = response.data.name
    } catch { /* 名称读取失败不影响固定版本引用；不展示旧账号或旧版本名称。 */ }
  }, { immediate: true })
  onBeforeUnmount(() => controller?.abort())
  return name
}
