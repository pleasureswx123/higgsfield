import { computed, onBeforeUnmount, ref } from 'vue'
import type { ReferenceCandidate } from '@/api/references'
import { useReferencePreview } from './useReferencePreview'
import { useReferenceUploads } from './useReferenceUploads'
import { cropPixels, type CropRect } from '@/utils/imageCrop'

/** 裁剪结果走既有上传与新增素材流程，不覆盖源版本。 */
export function useReferenceCrop(projectId: string, folder: () => string | null, visible: () => boolean, saved: () => void) {
  const preview = useReferencePreview(visible)
  const exporting = ref(false), error = ref('')
  let alive = true
  const uploads = useReferenceUploads(projectId, folder, () => !visible(), saved)
  const item = computed(() => uploads.items.at(-1))
  const locked = computed(() => exporting.value || uploads.checking.value || uploads.running.value)
  const frozen = computed(() => locked.value || Boolean(item.value))
  async function show(row: ReferenceCandidate) { await preview.show(row) }
  async function confirm(image: HTMLImageElement, rect: CropRect) {
    if (frozen.value || !visible() || !preview.url.value || !image.naturalWidth) return
    exporting.value = true; error.value = ''
    const source = preview.url.value
    try {
      const pixels = cropPixels(rect, image.naturalWidth, image.naturalHeight)
      const canvas = document.createElement('canvas')
      canvas.width = pixels.width; canvas.height = pixels.height
      const context = canvas.getContext('2d')
      if (!context) throw new Error('浏览器无法创建裁剪画布')
      context.drawImage(image, pixels.x, pixels.y, pixels.width, pixels.height, 0, 0, pixels.width, pixels.height)
      const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('裁剪导出失败，请缩小裁剪范围后重试')), 'image/png'))
      if (!alive || !visible() || source !== preview.url.value) return
      const name = (preview.candidate.value?.displayName || '图片').replace(/\.[^.]+$/, '').slice(0, 170)
      await uploads.enqueue([new File([blob], `${name}-裁剪.png`, { type: 'image/png' })])
    } catch (cause) { if (alive) error.value = cause instanceof Error ? cause.message : '裁剪失败' }
    finally { if (alive) exporting.value = false }
  }
  onBeforeUnmount(() => { alive = false })
  return { preview, uploads, item, locked, frozen, error, show, confirm }
}
