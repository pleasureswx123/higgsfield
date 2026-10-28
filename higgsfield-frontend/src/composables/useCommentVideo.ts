import { nextTick, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import type { CommentTarget } from '@/api/comments'
import { readMedia } from '@/api/assets'
import { getOutputMedia } from '@/api/generations'
import { useAuthStore } from '@/stores/auth'
import { validCommentVideoTime, playerTimeToComment } from '@/utils/commentVideoTime'

export function useCommentVideo(target: () => CommentTarget, visible: () => boolean = () => true) {
  const auth = useAuthStore()
  let active = visible(), mountedActive = true,
    alive = true
  const available = () => alive && active && Boolean(auth.token)
  const player = ref<HTMLVideoElement>(),
    url = ref(''),
    loading = ref(false),
    error = ref('')
  let controller: AbortController | undefined, requested: number | undefined
  function clear() {
    controller?.abort()
    player.value?.pause()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
    loading.value = false
    error.value = ''
    requested = undefined
  }
  function seekReady() {
    if (!available() || !url.value) return
    const video = player.value
    if (!video || requested === undefined || video.readyState < 1) return
    if (!Number.isFinite(video.duration) || requested > video.duration) {
      error.value = '评论时间点超过当前视频可播放时长。'
    } else {
      video.pause()
      video.currentTime = requested
    }
    requested = undefined
  }
  async function open(time?: string) {
    if (!available()) return
    if (time !== undefined && !validCommentVideoTime(time)) {
      error.value = '无效的视频时间点'
      return
    }
    requested = time === undefined ? undefined : Number(time)
    error.value = ''
    if (url.value) {
      const current = controller
      await nextTick()
      if (current !== controller || current?.signal.aborted) return
      seekReady()
      return
    }
    if (loading.value) return
    const current = new AbortController()
    controller = current
    loading.value = true
    const value = target()
    try {
      const blob =
        'assetVersionId' in value
          ? await readMedia(value.assetVersionId, false, current.signal, () => {})
          : await getOutputMedia(value.outputId, false, current.signal)
      if (current.signal.aborted) return
      url.value = URL.createObjectURL(blob)
      await nextTick()
      if (!current.signal.aborted) seekReady()
    } catch (cause) {
      if (!current.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '视频读取失败'
    } finally {
      if (!current.signal.aborted) loading.value = false
    }
  }
  function currentTime() {
    return available() && url.value && player.value
      ? playerTimeToComment(player.value.currentTime)
      : ''
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
  return { player, url, loading, error, open, seekReady, currentTime }
}
