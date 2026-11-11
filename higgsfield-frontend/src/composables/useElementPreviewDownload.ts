import { onBeforeUnmount, ref, watch } from 'vue'
import { readAssetVersion } from '@/api/assets'
import { useAssetBatchDownload } from './useAssetBatchDownload'

/** 下载当前固定素材版本，沿用素材授权下载链。 */
export function useElementPreviewDownload(allowed: () => boolean) {
  const selection = ref<string[]>([])
  const downloader = useAssetBatchDownload(() => [], selection, allowed)
  const resolving = ref(false)
  let controller: AbortController | undefined
  function stop() { controller?.abort(); downloader.stop() }
  async function download(version: string) {
    if (!allowed() || resolving.value || downloader.pending.value) return
    const current = new AbortController()
    controller = current
    resolving.value = true
    downloader.message.value = ''
    try {
      const result = await readAssetVersion(version, current.signal)
      if (!current.signal.aborted && allowed()) await downloader.downloadOne(result.data)
    } catch (cause) {
      if (!current.signal.aborted) downloader.message.value = cause instanceof Error ? cause.message : '下载失败，请重试'
    } finally { resolving.value = false }
  }
  watch(allowed, value => { if (!value) stop() })
  onBeforeUnmount(stop)
  return { ...downloader, resolving, download }
}
