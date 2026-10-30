<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElDialog } from 'element-plus'
import type { ReferenceCandidate } from '@/api/references'
import Button from '@/components/ui/Button.vue'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { useReferenceCrop } from '@/composables/useReferenceCrop'
import { changeCrop, cropPixels, type CropHandle, type CropRect } from '@/utils/imageCrop'

const props = defineProps<{ candidate: ReferenceCandidate; projectId: string; folderId: string | null; visible: boolean }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const crop = useReferenceCrop(props.projectId, () => props.folderId, () => props.visible, () => emit('saved'))
const stage = ref<HTMLElement>(), picture = ref<HTMLImageElement>(), frame = ref<HTMLElement>()
const dimensions = ref({ width: 0, height: 0 })
const available = ref({ width: 0, height: 0 })
const rect = ref<CropRect>({ x: 0, y: 0, width: 1, height: 1 })
const fitted = computed(() => {
  const scale = Math.min(available.value.width / (dimensions.value.width || 1), available.value.height / (dimensions.value.height || 1))
  return { width: `${dimensions.value.width * scale}px`, height: `${dimensions.value.height * scale}px` }
})
const selectionStyle = computed(() => ({ left: `${rect.value.x * 100}%`, top: `${rect.value.y * 100}%`, width: `${rect.value.width * 100}%`, height: `${rect.value.height * 100}%` }))
const pixels = computed(() => cropPixels(rect.value, dimensions.value.width || 1, dimensions.value.height || 1))
const handles: { key: CropHandle; label: string; left: string; top: string }[] = [
  { key: 'nw', label: '左上角', left: '0%', top: '0%' }, { key: 'n', label: '上边', left: '50%', top: '0%' },
  { key: 'ne', label: '右上角', left: '100%', top: '0%' }, { key: 'e', label: '右边', left: '100%', top: '50%' },
  { key: 'se', label: '右下角', left: '100%', top: '100%' }, { key: 's', label: '下边', left: '50%', top: '100%' },
  { key: 'sw', label: '左下角', left: '0%', top: '100%' }, { key: 'w', label: '左边', left: '0%', top: '50%' },
]
let observer: ResizeObserver | undefined
let dragging: { id: number; x: number; y: number; rect: CropRect; handle: CropHandle; width: number; height: number } | undefined
function observeStage() {
  observer?.disconnect()
  if (!stage.value) return
  const update = () => {
    if (stage.value) available.value = { width: Math.max(0, stage.value.clientWidth - 32), height: Math.max(0, stage.value.clientHeight - 32) }
  }
  observer = new ResizeObserver(update); observer.observe(stage.value); update()
}
function loaded() {
  if (picture.value) dimensions.value = { width: picture.value.naturalWidth, height: picture.value.naturalHeight }
  observeStage()
}
function start(event: PointerEvent, handle: CropHandle) {
  if (crop.frozen.value || !frame.value || event.button !== 0) return
  event.preventDefault()
  const bounds = frame.value.getBoundingClientRect()
  dragging = { id: event.pointerId, x: event.clientX, y: event.clientY, rect: { ...rect.value }, handle, width: bounds.width, height: bounds.height }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (!dragging || dragging.id !== event.pointerId || crop.frozen.value) return
  rect.value = changeCrop(dragging.rect, dragging.handle, (event.clientX - dragging.x) / dragging.width, (event.clientY - dragging.y) / dragging.height)
}
function keyboard(event: KeyboardEvent, handle: CropHandle) {
  if (crop.frozen.value || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const step = event.shiftKey ? 0.05 : 0.005
  rect.value = changeCrop(rect.value, handle, event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0, event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0)
}
function close() { if (!crop.locked.value) emit('close') }
onMounted(() => { void crop.show(props.candidate) })
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <ElDialog :model-value="visible" width="min(800px, 96vw)" top="5vh" append-to-body class="reference-crop-dialog" :before-close="close" :show-close="!crop.locked.value" :close-on-press-escape="!crop.locked.value" :close-on-click-modal="false" @opened="observeStage">
    <template #header="{ titleId, titleClass }"><DialogHeading :title-id="titleId" :title-class="titleClass" title="裁剪参考图片" /></template>
    <div ref="stage" class="crop-stage">
      <p v-if="crop.preview.loading.value" role="status">正在读取原图…</p>
      <p v-else-if="crop.preview.error.value" role="alert">{{ crop.preview.error.value }}</p>
      <div v-if="crop.preview.url.value" ref="frame" class="crop-frame" :style="fitted">
        <img ref="picture" :src="crop.preview.url.value" :alt="candidate.displayName" draggable="false" @load="loaded" @error="crop.error.value = '原图解码失败，请关闭后重试'" />
        <div v-if="dimensions.width" class="crop-selection" :style="selectionStyle" @pointermove="move" @pointerup="dragging = undefined" @pointercancel="dragging = undefined">
          <button class="crop-move" aria-label="移动裁剪框，使用方向键微调" :disabled="crop.frozen.value" @pointerdown="start($event, 'move')" @keydown="keyboard($event, 'move')"><span class="crop-grid" /></button>
          <button v-for="handle in handles" :key="handle.key" class="crop-handle" :style="{ left: handle.left, top: handle.top, cursor: `${handle.key}-resize` }" :aria-label="`调整裁剪框${handle.label}`" :disabled="crop.frozen.value" @pointerdown.stop="start($event, handle.key)" @keydown="keyboard($event, handle.key)" />
        </div>
      </div>
    </div>
    <p v-if="crop.error.value || crop.uploads.error.value || crop.item.value?.error" class="crop-error" role="alert">{{ crop.error.value || crop.uploads.error.value || crop.item.value?.error }}</p>
    <template #footer>
      <div class="crop-footer">
        <span class="muted" role="status">{{ crop.locked.value ? `正在新增素材… ${crop.item.value?.progress || 0}%` : `${pixels.width} × ${pixels.height} · 保存为新素材，保留原图` }}</span>
        <Button variant="outline" :disabled="crop.locked.value" @click="close">取消</Button>
        <Button v-if="crop.item.value && ['failed', 'paused'].includes(crop.item.value.stage)" :disabled="crop.locked.value" @click="crop.uploads.retry(crop.item.value)">重试新增素材</Button>
        <Button v-else :disabled="!dimensions.width || crop.frozen.value || Boolean(crop.preview.error.value)" @click="picture && crop.confirm(picture, rect)">{{ crop.locked.value ? '处理中…' : '确认' }}</Button>
      </div>
    </template>
  </ElDialog>
</template>

<style>
.reference-crop-dialog { border-radius: 24px; }
.reference-crop-dialog .el-dialog__body { padding: 0; }
</style>
<style scoped>
.crop-stage { height: min(560px, 65dvh); display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 18px; background: var(--background); }
.crop-frame { position: relative; flex-shrink: 0; }
.crop-frame > img { display: block; width: 100%; height: 100%; user-select: none; }
.crop-selection { position: absolute; border: 1px solid white; box-shadow: 0 0 0 2000px #0008; touch-action: none; }
.crop-move { position: absolute; inset: 0; width: 100%; height: 100%; padding: 0; border: 0; background: transparent; cursor: move; touch-action: none; }
.crop-grid { position: absolute; inset: 0; pointer-events: none; background: linear-gradient(to right, transparent 33.1%, #ffffff50 33.1%, #ffffff50 33.4%, transparent 33.4%, transparent 66.4%, #ffffff50 66.4%, #ffffff50 66.7%, transparent 66.7%), linear-gradient(to bottom, transparent 33.1%, #ffffff50 33.1%, #ffffff50 33.4%, transparent 33.4%, transparent 66.4%, #ffffff50 66.4%, #ffffff50 66.7%, transparent 66.7%); }
.crop-handle { position: absolute; width: 11px; height: 11px; border: 1px solid #555; border-radius: 4px; background: white; padding: 0; transform: translate(-50%, -50%); touch-action: none; }
.crop-handle:focus-visible, .crop-move:focus-visible { outline: 3px solid var(--primary); outline-offset: 3px; }
.crop-footer { display: flex; align-items: center; gap: 8px; padding-top: 12px; }
.crop-footer > span { margin-right: auto; text-align: left; font-size: 12px; }
.crop-error { margin: 8px 0; color: var(--destructive); }
</style>
