import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { readMedia } from '@/api/assets'
import { getOutputMedia } from '@/api/generations'
import type { CommentTarget } from '@/api/comments'
import { useAuthStore } from '@/stores/auth'
export function useCommentImage(target: () => CommentTarget, visible: () => boolean = () => true) {
  const auth = useAuthStore()
  let active = visible(), mountedActive = true,
    alive = true
  const available = () => alive && active && Boolean(auth.token)
  const url = ref(''),
    loading = ref(false),
    error = ref('')
  let controller: AbortController | undefined
  function clear() {
    controller?.abort()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
    loading.value = false
    error.value = ''
  }
  async function open() {
    if (!available() || loading.value || url.value) return
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = ''
    const value = target()
    try {
      const blob =
        'assetVersionId' in value
          ? await readMedia(value.assetVersionId, false, current.signal, () => {})
          : await getOutputMedia(value.outputId, false, current.signal)
      if (!current.signal.aborted) url.value = URL.createObjectURL(blob)
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '图片读取失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  watch(
    [
      () => JSON.stringify(target()),
      () => auth.token,
      () => JSON.stringify(auth.user?.permissions || []),
    ],
    clear,
    { flush: 'sync' },
  )
  onDeactivated(() => {
    mountedActive = false
    active = false
    clear()
  })
  onActivated(() => {
    mountedActive = true
    active = visible()
  })
  watch(visible, value => {
    active = value && mountedActive
    if (!active) clear()
  }, { flush: 'sync' })
  onBeforeUnmount(() => {
    alive = false
    active = false
    clear()
  })
  return { url, loading, error, open }
}
