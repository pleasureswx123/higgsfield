<script setup lang="ts">
import { computed, ref } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import { ElDialog } from 'element-plus'
import { IconZoomIn, IconZoomOut, IconDownload, IconX } from '@tabler/icons-vue'

defineProps<{ url: string; downloadDisabled: boolean }>()
const emit = defineEmits<{ close: []; download: [] }>()
const stage = ref<HTMLElement>()
const image = ref<HTMLImageElement>()
const fit = ref(1)
const scale = ref(1)
const offset = ref({ x: 0, y: 0 })
const dragging = ref(false)
const ready = ref(false)
const failed = ref(false)
const natural = ref({ width: 0, height: 0 })
const min = computed(() => Math.min(0.2, fit.value))
const max = computed(() => Math.max(5, fit.value))
const label = computed(() => `${Math.round(scale.value * 100)}%`)
const imageStyle = computed(() => ({ width: `${natural.value.width * scale.value}px`, height: `${natural.value.height * scale.value}px`, transform: `translate(${offset.value.x}px, ${offset.value.y}px)` }))
let drag: { id: number; x: number; y: number; left: number; top: number } | undefined
function clampOffset(x: number, y: number) {
  const limitX = Math.max(0, ((image.value?.naturalWidth || 0) * scale.value - (stage.value?.clientWidth || 0)) / 2)
  const limitY = Math.max(0, ((image.value?.naturalHeight || 0) * scale.value - (stage.value?.clientHeight || 0)) / 2)
  offset.value = { x: Math.max(-limitX, Math.min(limitX, x)), y: Math.max(-limitY, Math.min(limitY, y)) }
}
function stop() {
  if (drag && stage.value?.hasPointerCapture(drag.id)) stage.value.releasePointerCapture(drag.id)
  drag = undefined
  dragging.value = false
}
function reset() { stop(); scale.value = fit.value; offset.value = { x: 0, y: 0 } }
function measure() {
  if (!stage.value || !image.value?.naturalWidth) return
  natural.value = { width: image.value.naturalWidth, height: image.value.naturalHeight }
  const wasFit = Math.abs(scale.value - fit.value) < 0.001
  fit.value = Math.min(1, stage.value.clientWidth / image.value.naturalWidth, stage.value.clientHeight / image.value.naturalHeight)
  if (!ready.value || wasFit) reset()
  else clampOffset(offset.value.x, offset.value.y)
  ready.value = true
}
useResizeObserver(stage, measure)
function zoom(value: number, x?: number, y?: number) {
  if (!ready.value) return
  stop()
  const bounds = stage.value!.getBoundingClientRect()
  const px = x === undefined ? 0 : x - bounds.left - bounds.width / 2
  const py = y === undefined ? 0 : y - bounds.top - bounds.height / 2
  const next = Math.max(min.value, Math.min(max.value, value))
  const ratio = next / scale.value
  scale.value = next
  clampOffset(px - (px - offset.value.x) * ratio, py - (py - offset.value.y) * ratio)
}
function wheel(event: WheelEvent) {
  zoom(scale.value * Math.exp(-Math.max(-100, Math.min(100, event.deltaY)) * 0.002), event.clientX, event.clientY)
}
function toggleActual() {
  if (Math.abs(scale.value - fit.value) > 0.001) reset()
  else { zoom(1); offset.value = { x: 0, y: 0 } }
}
function start(event: PointerEvent) {
  if (event.button !== 0 || scale.value <= fit.value || !ready.value) return
  event.preventDefault()
  stage.value!.setPointerCapture(event.pointerId)
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: offset.value.x, top: offset.value.y }
  dragging.value = true
}
function move(event: PointerEvent) {
  if (drag?.id === event.pointerId) clampOffset(drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y)
}
</script>

<template>
  <ElDialog :model-value="true" title="图片放大预览" fullscreen append-to-body class="element-image-lightbox" :show-close="false" @close="emit('close')">
    <div ref="stage" class="element-image-lightbox-stage" :class="{ pannable: scale > fit, dragging }" @wheel.prevent="wheel" @dblclick="toggleActual" @pointermove="move" @pointerup="stop" @pointercancel="stop" @lostpointercapture="stop">
      <img ref="image" :src="url" alt="素材放大预览" :style="imageStyle" :draggable="false" @load="measure" @error="failed = true" @pointerdown="start" />
      <span v-if="failed" role="alert">图片加载失败，请关闭后重试</span>
    </div>
    <div class="element-image-lightbox-tools">
      <button aria-label="缩小" title="缩小" :disabled="!ready || scale <= min" @click="zoom(scale / 1.2)"><IconZoomOut :size="18" /></button>
      <button class="scale-label" aria-label="适应窗口并居中" title="适应窗口并居中；双击图片切换原始尺寸" :disabled="!ready" @click="reset">{{ label }}</button>
      <button aria-label="放大" title="放大" :disabled="!ready || scale >= max" @click="zoom(scale * 1.2)"><IconZoomIn :size="18" /></button>
      <button aria-label="下载原素材" title="下载原素材" :disabled="downloadDisabled" @click="emit('download')"><IconDownload :size="18" /></button>
      <button aria-label="关闭放大预览" title="关闭放大预览" @click="emit('close')"><IconX :size="18" /></button>
    </div>
  </ElDialog>
</template>

<style>
html:has(.element-image-lightbox) { scrollbar-gutter: auto; }
.el-dialog.element-image-lightbox.is-fullscreen { width: 100vw; height: 100dvh; max-width: none; margin: 0; padding: 0; background: rgb(0 0 0 / 94%); backdrop-filter: blur(8px); overflow: hidden; }
.element-image-lightbox .el-dialog__header { position: absolute; width: 1px; height: 1px; overflow: hidden; padding: 0; clip-path: inset(50%); }
.element-image-lightbox .el-dialog__body { height: 100%; padding: 0; }
.element-image-lightbox-stage { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; overflow: hidden; touch-action: none; user-select: none; color: white; }
.element-image-lightbox-stage img { flex: none; max-width: none; max-height: none; border-radius: 0; }
.element-image-lightbox-stage.pannable { cursor: grab; }
.element-image-lightbox-stage.dragging { cursor: grabbing; }
.element-image-lightbox-tools { position: absolute; top: 16px; right: 16px; display: flex; gap: 8px; }
.element-image-lightbox-tools button { display: grid; place-items: center; width: 40px; height: 40px; border: 1px solid #ffffff08; border-radius: 12px; background: #181818; color: #bdbdbd; cursor: pointer; }
.element-image-lightbox-tools button:hover { background: #292929; color: white; }
.element-image-lightbox-tools button:disabled { opacity: .35; cursor: default; }
.element-image-lightbox-tools button:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.element-image-lightbox-tools .scale-label { width: 64px; font-size: 12px; font-variant-numeric: tabular-nums; }
</style>
