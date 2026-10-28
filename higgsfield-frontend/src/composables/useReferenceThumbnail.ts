import { onActivated, onDeactivated, onBeforeUnmount, ref, watch } from 'vue'
import { readThumbnail, readMedia } from '@/api/assets'
import { useAuthStore } from '@/stores/auth'
/** 只读取固定版本的派生缩略图，页面隐藏或授权变化时清理。 */
export function useReferenceThumbnail(version: () => string, visible: () => boolean, allowOriginal: () => boolean = () => false) {
  const auth = useAuthStore(), url = ref(''), loading = ref(false), error = ref('')
  let active = true, reader: AbortController | undefined
  function clear() {
    reader?.abort()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''; loading.value = false; error.value = ''
  }
  async function load() {
    clear()
    if (!active || !auth.token || !visible() || !version()) return
    const controller = new AbortController(); reader = controller; loading.value = true
    try {
      let blob: Blob
      try { blob = await readThumbnail(version(), controller.signal) }
      catch (cause) {
        if (controller.signal.aborted || !allowOriginal() || (cause as { errorCode?: string }).errorCode !== 'THUMBNAIL_NOT_READY') throw cause
        // 派生图未就绪时，小图片可经同一授权预览接口读取，不使用供应商地址。
        blob = await readMedia(version(), false, controller.signal, () => {})
      }
      if (controller.signal.aborted) return
      if (!['image/webp', ...(allowOriginal() ? ['image/png', 'image/jpeg'] : [])].includes(blob.type)) throw new Error('此引用不是可显示的图片缩略图')
      url.value = URL.createObjectURL(blob)
    } catch (cause) { if (!controller.signal.aborted) error.value = cause instanceof Error ? cause.message : '预览不可用' }
    finally { if (!controller.signal.aborted) loading.value = false }
  }
  watch(() => [version(), visible(), auth.token, JSON.stringify(auth.user?.permissions || [])], () => { void load() }, { immediate: true, flush: 'sync' })
  onDeactivated(() => { active = false; clear() })
  onActivated(() => { if (!active) { active = true; void load() } })
  onBeforeUnmount(() => { active = false; clear() })
  function mediaFailed(source: string) {
    if (!active || !source || source !== url.value) return
    clear()
    error.value = '浏览器无法解码缩略图，请重试或查看原图。'
  }
  return { url, loading, error, load, mediaFailed }
}
