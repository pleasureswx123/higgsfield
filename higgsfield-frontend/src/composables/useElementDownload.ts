import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { readElement, type ElementRecord } from '@/api/elements'
import { readMedia } from '@/api/assets'
import { assetExtension } from '@/utils/assetFormats'
import { useAuthStore } from '@/stores/auth'

/** 下载已保存修订的全部图片；每个版本仍由媒体接口独立鉴权。 */
export function useElementDownload(
  allowed: () => boolean,
  completed: (ids: string[]) => void = () => {},
) {
  const auth = useAuthStore(),
    pending = ref(false),
    message = ref(''),
    currentName = ref(''),
    loadedBytes = ref(0)
  let active = true,
    epoch = 0,
    stopped = false,
    reader: AbortController | undefined
  const delivered = new Map<string, Set<string>>()
  const urls = new Map<string, ReturnType<typeof setTimeout>>()
  function release(url: string) {
    clearTimeout(urls.get(url))
    urls.delete(url)
    URL.revokeObjectURL(url)
  }
  function stop() {
    stopped = true
    reader?.abort()
  }
  function clear() {
    stop()
    epoch++
    pending.value = false
    message.value = ''
    currentName.value = ''
    loadedBytes.value = 0
    delivered.clear()
    for (const url of urls.keys()) release(url)
  }
  async function download(values: ElementRecord[]) {
    if (!active || !auth.token || !allowed() || pending.value) return
    const items = [...new Map(values.map((item) => [item.id, { ...item }])).values()]
    if (!items.length) return
    const ticket = epoch,
      failures: string[] = [],
      done: string[] = []
    const valid = () => ticket === epoch && active && !stopped && !!auth.token && allowed()
    let count = 0
    stopped = false
    pending.value = true
    message.value = ''
    try {
      for (const item of items) {
        if (!valid()) break
        const controller = (reader = new AbortController())
        const key = `${item.id}:${item.currentRevisionId}`
        currentName.value = item.name
        loadedBytes.value = 0
        try {
          const { data } = await readElement(item.id, controller.signal)
          if (!valid() || controller.signal.aborted) break
          if (
            data.element.projectId !== item.projectId ||
            data.currentRevision.id !== item.currentRevisionId
          )
            throw new Error('元素已变化，请刷新后重新选择')
          const media = [
            ...new Map(
              data.currentRevision.media.map((image) => [image.assetVersionId, { ...image }]),
            ).values(),
          ].sort((a, b) => a.ordinal - b.ordinal)
          if (!media.length) throw new Error('此修订没有可下载图片')
          const sent = delivered.get(key) || new Set<string>()
          delivered.set(key, sent)
          for (const [index, image] of media.entries()) {
            if (!valid() || controller.signal.aborted) break
            if (sent.has(image.assetVersionId)) continue
            currentName.value = `${item.name}（${index + 1}/${media.length}）`
            loadedBytes.value = 0
            try {
              const blob = await readMedia(
                image.assetVersionId,
                true,
                controller.signal,
                (bytes) => {
                  if (valid() && !controller.signal.aborted) loadedBytes.value = bytes
                },
              )
              if (!valid() || controller.signal.aborted) break
              if (!blob.type.startsWith('image/')) throw new Error('返回内容不是图片，未触发下载')
              const url = URL.createObjectURL(blob),
                anchor = document.createElement('a')
              urls.set(
                url,
                setTimeout(() => release(url), 60000),
              )
              const name = item.name.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').slice(0, 120)
              anchor.href = url
              anchor.download = `${name}-${index + 1}-${image.assetVersionId}${assetExtension(blob.type)}`
              anchor.click()
              sent.add(image.assetVersionId)
              count++
            } catch (cause) {
              if (!valid() || controller.signal.aborted) break
              failures.push(
                `${item.name} 第 ${index + 1} 张：${cause instanceof Error ? cause.message : '读取失败'}`,
              )
            }
          }
          if (!valid() || controller.signal.aborted) break
          if (media.every((image) => sent.has(image.assetVersionId))) {
            delivered.delete(key)
            done.push(item.id)
          }
        } catch (cause) {
          if (!valid() || controller.signal.aborted) break
          failures.push(`${item.name}：${cause instanceof Error ? cause.message : '元素读取失败'}`)
        }
      }
      if (ticket !== epoch) return
      if (done.length) completed(done)
      message.value = `本次已交给浏览器 ${count} 个图片文件，${done.length} 个元素已完成交付。${items.length - done.length} 个元素未全部完成。${failures.join('；')}${stopped ? '；已停止。' : ''}请在浏览器下载列表确认保存结果；多文件下载可能需要浏览器允许。失败项重试会跳过本会话已交付的同修订图片。`
    } finally {
      if (ticket === epoch) {
        pending.value = false
        currentName.value = ''
        loadedBytes.value = 0
      }
    }
  }
  watch(() => auth.token, clear, { flush: 'sync' })
  watch(
    allowed,
    (value) => {
      if (!value) stop()
    },
    { flush: 'sync' },
  )
  watch(() => JSON.stringify(auth.user?.permissions || []), stop, { flush: 'sync' })
  onDeactivated(() => {
    active = false
    stop()
  })
  onActivated(() => {
    active = true
  })
  onBeforeUnmount(() => {
    active = false
    clear()
  })
  onBeforeRouteLeave(() => !pending.value)
  onBeforeRouteUpdate((to, from) => to.fullPath === from.fullPath || !pending.value)
  return { pending, message, currentName, loadedBytes, download, stop }
}
