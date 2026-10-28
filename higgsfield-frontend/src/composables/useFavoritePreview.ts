import { onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { readAsset, readMedia } from '@/api/assets'
import { getOutput, getOutputMedia } from '@/api/generations'
import type { Favorite } from '@/api/favorites'
import { useAuthStore } from '@/stores/auth'

export function useFavoritePreview() {
  const router = useRouter(),
    auth = useAuthStore()
  const assetOpen = ref(false),
    title = ref(''),
    url = ref('')
  const mediaType = ref(''),
    text = ref(''),
    notice = ref(''),
    loading = ref(false),
    error = ref('')
  let controller: AbortController | undefined
  function clear() {
    controller?.abort()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
    title.value = ''
    mediaType.value = ''
    error.value = ''
    loading.value = false
    assetOpen.value = false
    text.value = ''
    notice.value = ''
  }
  async function open(row: Favorite) {
    clear()
    if (!row.available || !row.source) return
    if ('elementId' in row.target && row.source.projectId) {
      await router.push({
        name: 'project-detail',
        params: { id: row.source.projectId },
        query: { tab: 'elements', element: row.target.elementId },
      })
      return
    }
    if (!('assetId' in row.target) && !('outputId' in row.target)) return
    const current = new AbortController()
    controller = current
    assetOpen.value = true
    loading.value = true
    try {
      if ('outputId' in row.target) {
        const { data: output } = await getOutput(row.target.outputId, current.signal)
        if (current.signal.aborted) return
        title.value = `作品 #${output.ordinal + 1}`
        mediaType.value = output.kind
        if (output.kind === 'text') {
          text.value = output.text || ''
          return
        }
        if (!output.previewUrl) {
          notice.value = '作品尚无可预览的归档文件。'
          return
        }
        const blob = await getOutputMedia(row.target.outputId, false, current.signal)
        if (!current.signal.aborted) url.value = URL.createObjectURL(blob)
        return
      }
      const result = await readAsset(row.target.assetId, current.signal)
      if (current.signal.aborted) return
      title.value = result.data.name
      mediaType.value = result.data.mediaType
      const blob = await readMedia(result.data.currentVersionId, false, current.signal, () => {})
      if (!current.signal.aborted) url.value = URL.createObjectURL(blob)
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '预览失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  watch(() => auth.token, clear, { flush: 'sync' })
  onDeactivated(clear)
  onBeforeUnmount(clear)
  return { assetOpen, title, url, mediaType, text, notice, loading, error, clear, open }
}
