import { onActivated, onBeforeUnmount, onDeactivated, ref, watch, type Ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { readMedia, type Asset } from '@/api/assets'
import { assetExtension } from '@/utils/assetFormats'
import { useAuthStore } from '@/stores/auth'

/** 每次只读取一个固定版本，下载仍由现有授权接口检查。 */
export function useAssetBatchDownload(rows: () => Asset[], selected: Ref<string[]>, allowed: () => boolean) {
  const auth = useAuthStore(), pending = ref(false), message = ref(''), currentName = ref(''), currentId = ref(''), loadedBytes = ref(0)
  let active = true, epoch = 0, stopped = false, reader: AbortController | undefined
  const urls = new Map<string, ReturnType<typeof setTimeout>>()
  function release(url: string) { clearTimeout(urls.get(url)); urls.delete(url); URL.revokeObjectURL(url) }
  function stop() { stopped = true; reader?.abort() }
  function clear() {
    stop(); epoch++; pending.value = false; message.value = ''; currentName.value = ''; currentId.value = ''; loadedBytes.value = 0
    for (const url of urls.keys()) release(url)
  }
  async function downloadItems(targets: Asset[], updateSelection: boolean) {
    if (!active || !auth.token || !allowed() || pending.value) return
    const items = [...new Map(targets.map(item => [item.id, { ...item, file: { ...item.file } }])).values()]
    if (!items.length) return
    const ticket = epoch, failures: string[] = []

    stopped = false; pending.value = true; message.value = ''
    try {
      for (const item of items) {
        if (ticket !== epoch || !active || stopped || !auth.token || !allowed()) break
        const controller = new AbortController(); reader = controller
        currentName.value = item.name; currentId.value = item.id; loadedBytes.value = 0
        try {
          const blob = await readMedia(item.currentVersionId, true, controller.signal, bytes => {
            if (ticket === epoch && !controller.signal.aborted) loadedBytes.value = bytes
          })
          if (ticket !== epoch || controller.signal.aborted || !active || !allowed()) break
          const url = URL.createObjectURL(blob), anchor = document.createElement('a')
          // 交给浏览器后延后释放，避免立即撤销使下载失效。
          urls.set(url, setTimeout(() => release(url), 60000))
          const extension = assetExtension(item.file.mimeType)
          anchor.href = url
          anchor.download = item.name.toLowerCase().endsWith(extension) ? item.name : item.name + extension
          anchor.click()
          if (updateSelection) selected.value = selected.value.filter(id => id !== item.id)
        } catch (cause) {
          if (ticket !== epoch || controller.signal.aborted) break
          failures.push(`${item.name}：${cause instanceof Error ? cause.message : '读取失败'}`)
        }
      }
      if (ticket !== epoch) return
      message.value = failures.length ? `下载失败：${failures.join('；')}。请重试。` : ''
    } finally {
      if (ticket === epoch) { pending.value = false; currentName.value = ''; currentId.value = ''; loadedBytes.value = 0 }
    }
  }
  function download() { return downloadItems(rows().filter(item => selected.value.includes(item.id)), true) }
  // 卡片下载不改变列表选择，也不触碰素材预览状态。
  function downloadOne(asset: Asset) { return downloadItems([asset], false) }
  watch(() => auth.token, clear, { flush: 'sync' })
  watch(allowed, value => { if (!value) stop() }, { flush: 'sync' })
  watch(() => JSON.stringify(auth.user?.permissions || []), stop, { flush: 'sync' })
  onDeactivated(() => { active = false; stop() })
  onActivated(() => { active = true })
  onBeforeUnmount(() => { active = false; clear() })
  onBeforeRouteLeave(() => !pending.value)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || !pending.value)
  return { pending, message, currentName, currentId, loadedBytes, download, downloadOne, stop }
}
