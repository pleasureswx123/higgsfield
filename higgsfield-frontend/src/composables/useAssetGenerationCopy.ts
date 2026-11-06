import { onBeforeUnmount, ref, watch } from 'vue'
import { getGeneration, type GenerationSnapshot } from '@/api/generations'
import { useGenerationCopy } from './useGenerationCopy'
import { useRoute } from 'vue-router'

/** 从已授权的来源任务载入完整输入，复用草稿幂等保存与路由恢复。 */
export function useAssetGenerationCopy(identity: () => string | undefined) {
  const snapshot = ref<GenerationSnapshot>()
  const loading = ref(false), error = ref('')
  const route = useRoute()
  const copy = useGenerationCopy(() => snapshot.value, () => {
    const folder = typeof route.query.folder === 'string' && /^[1-9]\d*$/.test(route.query.folder) ? route.query.folder : null
    const query: Record<string, string> = { tab: 'folders' }
    if (folder) query.folder = folder
    return { folderId: folder, query }
  })
  let request: AbortController | undefined
  function reset() {
    request?.abort()
    snapshot.value = undefined
    loading.value = false
    error.value = ''
  }
  watch(identity, reset)
  onBeforeUnmount(reset)
  async function load() {
    const id = identity()
    if (!id || loading.value || copy.pending.value) return
    loading.value = true
    error.value = ''
    const current = new AbortController()
    request = current
    try {
      if (!copy.retryable.value) {
        const result = await getGeneration(id, current.signal)
        if (current.signal.aborted || id !== identity()) return
        if (!result.data.allowedActions.includes('generation:copy-input'))
          throw new Error('暂无载入该任务创作参数的权限')
        snapshot.value = result.data
      }
      await copy.copy()
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '载入失败，请重试'
    } finally {
      if (request === current) loading.value = false
    }
  }
  return { loading, error, copyError: copy.error, load }
}
