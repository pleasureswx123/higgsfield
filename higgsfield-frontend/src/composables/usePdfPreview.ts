import { onActivated, onBeforeUnmount, onDeactivated, ref, watch, type Ref } from 'vue'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { pdfAssetBase } from '@/utils/pdfAssets'

export function usePdfPreview(
  source: () => Blob | null,
  canvas: Ref<HTMLCanvasElement | undefined>,
) {
  const page = ref(1),
    total = ref(0),
    scale = ref(1),
    loading = ref(false),
    error = ref('')
  let document: PDFDocumentProxy | undefined, task: PDFDocumentLoadingTask | undefined
  let rendering: RenderTask | undefined,
    epoch = 0,
    renderEpoch = 0
  let inactive = false
  function clear() {
    epoch++
    renderEpoch++
    rendering?.cancel()
    rendering = undefined
    void task?.destroy().catch(() => undefined)
    task = undefined
    document = undefined
    total.value = 0
    loading.value = false
    if (canvas.value) canvas.value.width = 0
  }
  async function render() {
    if (!document || !canvas.value) return
    rendering?.cancel()
    const current = ++renderEpoch,
      loaded = document
    loading.value = true
    error.value = ''
    try {
      const pdfPage = await loaded.getPage(page.value)
      if (current !== renderEpoch) return
      const viewport = pdfPage.getViewport({ scale: scale.value })
      const ratio = Math.min(
        window.devicePixelRatio || 1,
        2,
        Math.sqrt(16000000 / (viewport.width * viewport.height)),
      )
      // 每次使用独立画布，快速翻页时旧任务不会污染当前页面。
      const buffer = window.document.createElement('canvas')
      buffer.width = Math.max(1, Math.floor(viewport.width * ratio))
      buffer.height = Math.max(1, Math.floor(viewport.height * ratio))
      const run = pdfPage.render({
        canvas: buffer,
        viewport,
        transform: [ratio, 0, 0, ratio, 0, 0],
      })
      rendering = run
      await run.promise
      if (current !== renderEpoch || !canvas.value) return
      canvas.value.width = buffer.width
      canvas.value.height = buffer.height
      canvas.value.style.width = `${viewport.width}px`
      canvas.value.style.height = `${viewport.height}px`
      canvas.value.getContext('2d')?.drawImage(buffer, 0, 0)
    } catch (cause) {
      if (current === renderEpoch)
        error.value = cause instanceof Error ? cause.message : 'PDF页面读取失败'
    } finally {
      if (current === renderEpoch) loading.value = false
    }
  }
  async function load(blob: Blob | null) {
    clear()
    page.value = 1
    scale.value = 1
    error.value = ''
    if (!blob || inactive) return
    const current = epoch
    loading.value = true
    try {
      // 仅打开 PDF 时读取解析器；关闭或换文件后不启动迟到的解析任务。
      const [pdf, bytes] = await Promise.all([import('pdfjs-dist'), blob.arrayBuffer()])
      if (current !== epoch || inactive) return
      pdf.GlobalWorkerOptions.workerSrc = workerUrl
      const data = new Uint8Array(bytes)
      task = pdf.getDocument({
        data,
        useSystemFonts: true,
        cMapUrl: `${pdfAssetBase}cmaps/`,
        cMapPacked: true,
        standardFontDataUrl: `${pdfAssetBase}standard_fonts/`,
        wasmUrl: `${pdfAssetBase}wasm/`,
        iccUrl: `${pdfAssetBase}iccs/`,
      })
      const opening = task
      opening.onPassword = () => {
        if (current !== epoch) return
        error.value = '加密PDF请下载后输入密码查看'
        loading.value = false
        void opening.destroy().catch(() => undefined)
      }
      const loaded = await task.promise
      if (current !== epoch) return
      document = loaded
      total.value = loaded.numPages
      await render()
    } catch (cause) {
      if (current === epoch) {
        error.value ||= cause instanceof Error ? cause.message : 'PDF加载失败'
        loading.value = false
      }
    }
  }
  watch(source, load, { immediate: true })
  watch([page, scale, canvas], () => {
    void render()
  })
  onDeactivated(() => {
    inactive = true
    clear()
  })
  onActivated(() => {
    if (inactive) {
      inactive = false
      void load(source())
    }
  })
  onBeforeUnmount(clear)
  return { page, total, scale, loading, error }
}
