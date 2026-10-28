import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getOutputMedia, getOutputThumbnail, type GenerationSummary } from '@/api/generations'

/** 图片进入视口后读取派生缩略图；视频需主动打开，避免自动下载整段视频。 */
export function useGenerationCardMedia(preview: () => GenerationSummary['cardPreview'], visible: () => boolean) {
  const auth = useAuthStore(), url = ref(''), loading = ref(false), error = ref('')
  let active = true, alive = true, reader: AbortController | undefined
  function clear() {
    reader?.abort()
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''; loading.value = false; error.value = ''
  }
  async function load() {
    clear()
    const source = preview()
    if (!alive || !active || !visible() || !auth.token || !source) return
    const current = reader = new AbortController()
    loading.value = true
    try {
      const blob = source.kind === 'image'
        ? await getOutputThumbnail(source.outputId, current.signal)
        : await getOutputMedia(source.outputId, false, current.signal)
      if (current.signal.aborted) return
      const types = source.kind === 'image' ? ['image/webp'] : ['video/mp4', 'video/webm']
      if (!types.includes(blob.type)) throw new Error('媒体类型与输出不一致')
      url.value = URL.createObjectURL(blob)
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '预览读取失败'
    } finally { if (!current.signal.aborted) loading.value = false }
  }
  function sync() { clear(); if (preview()?.kind === 'image') void load() }
  function mediaFailed(source: string) {
    if (!alive || !active || !source || source !== url.value) return
    clear()
    error.value = '浏览器无法解码此媒体，可重试或打开任务详情核查文件。'
  }
  watch(() => [preview()?.outputId, preview()?.revision, preview()?.kind, visible(), auth.token, JSON.stringify(auth.user?.permissions || [])], sync, { immediate: true, flush: 'sync' })
  onDeactivated(() => { active = false; clear() })
  onActivated(() => { if (!active) { active = true; sync() } })
  onBeforeUnmount(() => { alive = false; clear() })
  return { url, loading, error, load, mediaFailed }
}
