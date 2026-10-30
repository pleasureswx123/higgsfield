import { onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { readMedia } from '@/api/assets'
import type { ReferenceCandidate } from '@/api/references'
import { useAuthStore } from '@/stores/auth'

/** 预览固定素材版本；离开选择器或授权变化时取消读取并释放文件。 */
export function useReferencePreview(visible: () => boolean) {
  const auth = useAuthStore()
  const candidate = ref<Pick<ReferenceCandidate, 'displayName' | 'assetVersionIds' | 'primaryAssetVersionId' | 'allowedMediaRoles'> | null>(null)
  const url = ref(''), error = ref(''), loading = ref(false)
  let controller: AbortController | undefined
  function close() {
    controller?.abort()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''; error.value = ''; loading.value = false; candidate.value = null
  }
  async function show(row: Pick<ReferenceCandidate, 'displayName' | 'assetVersionIds' | 'primaryAssetVersionId' | 'allowedMediaRoles'>) {
    close()
    if (!visible() || !auth.token) return
    candidate.value = row
    const version = row.primaryAssetVersionId || row.assetVersionIds[0]
    if (!version) { error.value = '此候选没有可预览的素材'; return }
    const reader = new AbortController(); controller = reader; loading.value = true
    try {
      const blob = await readMedia(version, false, reader.signal, () => {})
      if (!reader.signal.aborted) url.value = URL.createObjectURL(blob)
    } catch (cause) {
      if (!reader.signal.aborted) error.value = cause instanceof Error ? cause.message : '预览读取失败'
    } finally { if (!reader.signal.aborted) loading.value = false }
  }
  watch(() => [visible(), auth.token, JSON.stringify(auth.user?.permissions || [])], close)
  onDeactivated(close)
  onBeforeUnmount(close)
  return { candidate, url, error, loading, show, close }
}
