import { computed, ref, watch, onDeactivated, onBeforeUnmount } from 'vue'
import useUserStore from '@/store/modules/user'
import { getPriceSource, downloadPriceSource } from '@/api/studio/prices'
import { saveAs } from 'file-saver'

export function usePriceSource(sourceIds) {
  const user = useUserStore()
  const allowed = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:read')
  )
  const selectedId = ref(''),
    source = ref(),
    loading = ref(false),
    error = ref(''),
    downloading = ref(false)
  let controller, downloadController
  function clear() {
    controller?.abort()
    downloadController?.abort()
    downloadController = undefined
    downloading.value = false
    controller = undefined
    selectedId.value = ''
    source.value = undefined
    loading.value = false
    error.value = ''
  }
  async function download() {
    if (!allowed.value || downloading.value || !source.value?.attachment || !sourceIds().includes(selectedId.value)) return
    const id = selectedId.value, attachment = source.value.attachment
    const current = new AbortController()
    downloadController = current
    downloading.value = true
    error.value = ''
    try {
      const blob = await downloadPriceSource(id, current.signal)
      if (downloadController !== current || !allowed.value) return
      // 框架业务错误可能以 HTTP 200 JSON 返回，不能保存成证据文件。
      if (!blob || blob.type?.includes('json') || String(blob.size) !== attachment.byteSize)
        throw new Error('附件下载失败或大小不一致，请重新读取证据后重试')
      saveAs(blob, attachment.fileName)
    } catch (cause) {
      if (downloadController === current) error.value = cause?.message || '附件下载失败'
    } finally {
      if (downloadController === current) {
        downloading.value = false
        downloadController = undefined
      }
    }
  }
  async function select(id) {
    clear()
    if (!allowed.value || !sourceIds().includes(id)) return
    selectedId.value = id
    const current = new AbortController()
    controller = current
    loading.value = true
    try {
      const response = await getPriceSource(id, current.signal)
      if (controller === current) source.value = response.data
    } catch (cause) {
      if (controller === current) error.value = cause?.message || '来源读取失败'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  watch(sourceIds, clear, { deep: true, flush: 'sync' })
  watch(allowed, clear, { flush: 'sync' })
  onDeactivated(clear)
  onBeforeUnmount(clear)
  return { allowed, selectedId, source, loading, downloading, error, select, clear, download }
}
