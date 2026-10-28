import { ref, watch, onBeforeUnmount, onDeactivated } from 'vue'
import { readMedia } from '@/api/assets'
import { useAuthStore } from '@/stores/auth'

/** 悬停时授权读取视频，离开后立即取消读取并释放媒体。 */
export function useAssetHoverVideo(version: () => string, enabled: () => boolean) {
  const url = ref(''), auth = useAuthStore()
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  function stop() {
    clearTimeout(timer)
    controller?.abort()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
  }
  function start() {
    stop()
    if (!enabled() || !auth.token) return
    timer = setTimeout(async () => {
      const current = new AbortController()
      controller = current
      try {
        const blob = await readMedia(version(), false, current.signal, () => {})
        if (!current.signal.aborted) url.value = URL.createObjectURL(blob)
      } catch { /* 预播不可用时保留封面，完整预览仍可点击打开。 */ }
    }, 180)
  }
  watch(() => [version(), enabled(), auth.token, JSON.stringify(auth.user?.permissions)], stop)
  onBeforeUnmount(stop)
  onDeactivated(stop)
  return { url, start, stop }
}

