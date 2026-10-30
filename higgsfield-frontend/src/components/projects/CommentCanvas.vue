<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { IconX } from '@tabler/icons-vue'
import type { Annotation, MediaComment } from '@/api/comments'
import { imagePoint, buildAnnotation, type AnnotationPoint } from '@/utils/commentAnnotation'
const props = defineProps<{
  host: HTMLElement
  width: number
  height: number
  drawing: boolean
  disabled: boolean
  color: string
  tool: 'path' | 'point'
  comments: MediaComment[]
  selectedId: string
  resolved?: boolean
  resolvedIds?: string[]
}>()
const annotations = defineModel<Annotation[]>({ required: true })
const emit = defineEmits<{ select: [id: string]; draft: []; cancel: [] }>()
const rect = ref({ width: 0, height: 0 }),
  svg = ref<SVGSVGElement>(),
  points = ref<AnnotationPoint[]>([]),
  pointer = ref<number>()
let observer: ResizeObserver | undefined
onMounted(() => {
  observer = new ResizeObserver(() => {
    rect.value = { width: props.host.clientWidth, height: props.host.clientHeight }
  })
  observer.observe(props.host)
})
function outside(event: PointerEvent) {
  if (!props.drawing && !(event.target as Element).closest('.comment-canvas-popup,.comment-pin'))
    emit('select', '')
}
onMounted(() => props.host.addEventListener('pointerdown', outside))
onBeforeUnmount(() => {
  observer?.disconnect()
  props.host.removeEventListener('pointerdown', outside)
})
const bounds = computed(() => {
  const scale = Math.min(rect.value.width / props.width, rect.value.height / props.height)
  const width = props.width * scale,
    height = props.height * scale
  return {
    left: `${(rect.value.width - width) / 2}px`,
    top: `${(rect.value.height - height) / 2}px`,
    width: `${width}px`,
    height: `${height}px`,
  }
})
const draft = computed(() =>
  buildAnnotation(props.tool, points.value, props.color, props.width, props.height),
)
const selected = computed(() => props.comments.find((item) => item.id === props.selectedId))
const marks = computed(() =>
  draft.value
    ? [...annotations.value, draft.value]
    : annotations.value.length
      ? annotations.value
      : selected.value?.annotations || [],
)
function anchor(items: Annotation[]) {
  const item = items[0]
  const p =
    item?.shape === 'path' ? (item.geometry.points as AnnotationPoint[])?.[0] : item?.geometry
  return { x: Number(p?.x || 0), y: Number(p?.y || 0) }
}
const popup = computed(() => {
  const items = annotations.value.length ? annotations.value : selected.value?.annotations || []
  const p = anchor(items)
  const right = Math.max(p.x, ...items.flatMap(item => item.shape === 'path' ? (item.geometry.points as AnnotationPoint[]).map(point => point.x) : [Number(item.geometry.x || 0) + Number(item.geometry.width || 0)]))
  return {
    left: `clamp(8px, ${right * 100}% + 12px, calc(100% - 372px))`,
    top: `clamp(8px, ${p.y * 100}%, calc(100% - 240px))`,
  }
})
function clear() {
  points.value = []
  pointer.value = undefined
}
watch(() => [props.drawing, props.disabled], clear)
function start(e: PointerEvent) {
  if (!props.drawing || props.disabled || e.button !== 0) return
  const p = imagePoint(e.clientX, e.clientY, svg.value!.getBoundingClientRect())
  if (!p) return
  pointer.value = e.pointerId
  points.value = [p]
  svg.value!.setPointerCapture(e.pointerId)
}
function move(e: PointerEvent) {
  if (pointer.value !== e.pointerId) return
  const p = imagePoint(e.clientX, e.clientY, svg.value!.getBoundingClientRect())
  if (p) points.value = props.tool === 'path' ? [...points.value.slice(0, 255), p] : [p]
}
function finish(e: PointerEvent) {
  if (pointer.value !== e.pointerId) return
  move(e)
  const mark = draft.value || buildAnnotation('point', points.value, props.color, props.width, props.height)
  if (mark) {
    annotations.value = [mark]
    emit('draft')
  }
  clear()
}
function path(item: Annotation) {
  return ((item.geometry.points as AnnotationPoint[]) || [])
    .map((p) => `${p.x * 1000},${p.y * 1000}`)
    .join(' ')
}
</script>
<template>
  <Teleport :to="host"
    ><div class="comment-canvas" :style="bounds">
      <svg
        ref="svg"
        class="comment-drawing"
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        :class="{ drawing: drawing && !disabled }"
        aria-label="原图评论画布"
        @pointerdown="start"
        @pointermove="move"
        @pointerup="finish"
        @pointercancel="clear"
        @lostpointercapture="clear"
      >
        <g
          v-for="(item, index) in marks"
          :key="index"
          :stroke="item.color"
          fill="none"
          stroke-width="2"
        >
          <polyline
            v-if="item.shape === 'path'"
            :points="path(item)"
            vector-effect="non-scaling-stroke"
          />
          <circle
            v-else-if="item.shape === 'point'"
            :cx="Number(item.geometry.x) * 1000"
            :cy="Number(item.geometry.y) * 1000"
            r="6"
            vector-effect="non-scaling-stroke"
          />
          <rect
            v-else
            :x="Number(item.geometry.x) * 1000"
            :y="Number(item.geometry.y) * 1000"
            :width="Number(item.geometry.width) * 1000"
            :height="Number(item.geometry.height) * 1000"
            vector-effect="non-scaling-stroke"
          />
        </g>
      </svg>
      <span v-if="annotations.length" class="comment-pin active draft-pin" :style="{left: `${anchor(annotations).x * 100}%`, top: `${anchor(annotations).y * 100}%`}">我</span>
      <button type="button"
        v-for="item in comments.filter((value) => !value.deleted && value.annotations.length)"
        :key="item.id"
        class="comment-pin"
        :class="{ active: selectedId === item.id, resolved: resolvedIds?.includes(item.id) }"
        :style="{
          left: `${anchor(item.annotations).x * 100}%`,
          top: `${anchor(item.annotations).y * 100}%`,
        }"
        :aria-label="`查看评论 ${item.id}`"
        @click="emit('select', item.id)"
      >
        {{ item.author?.displayName.slice(0, 1) || '评' }}
      </button>
      <div
        v-if="annotations.length || selected"
        class="comment-canvas-popup"
        :style="popup"
        @pointerdown.stop
      >
        <slot v-if="annotations.length" name="draft" />
        <template v-else-if="selected"
          ><header>
            <strong>评论</strong><slot name="thread-tools" /><button type="button"
              aria-label="关闭评论浮层" title="关闭"
              @click="emit('select', '')"
            >
              <IconX :size="18" />
            </button>
          </header>
          <slot name="comment" :comment="selected"
        /></template>
      </div></div
  ></Teleport>
</template>
<style scoped>
.comment-canvas {
  position: absolute;
  pointer-events: none;
  z-index: 3;
}
.comment-drawing {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.comment-drawing.drawing {
  pointer-events: auto;
  touch-action: none;
  /* 光标热点位于笔尖，白色轮廓兼顾明暗画面。 */
  cursor: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2232%22%20height%3D%2232%22%20viewBox%3D%220%200%2032%2032%22%3E%3Cpath%20d%3D%22M5%2027l2-8L23%203a3%203%200%200%201%204%204L11%2023z%22%20fill%3D%22%23fff%22%20stroke%3D%22%23171819%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%2F%3E%3Cpath%20d%3D%22M8%2019L23%204l4%204-15%2015z%22%20fill%3D%22%23f4d42a%22%2F%3E%3Cpath%20d%3D%22M8%2019l4%204M21%206l5%205%22%20fill%3D%22none%22%20stroke%3D%22%23171819%22%20stroke-width%3D%222%22%2F%3E%3Cpath%20d%3D%22M5%2027l2-5%203%203z%22%20fill%3D%22%23171819%22%2F%3E%3C%2Fsvg%3E") 5 27, crosshair;
}
.draft-pin { display: grid; place-items: center; }
.comment-pin {
  position: absolute;
  transform: translate(-50%, -50%);
  width: 30px;
  height: 30px;
  border: 2px solid white;
  border-radius: 50% 50% 50% 3px;
  background: var(--surface-raised);
  color: var(--foreground);
  cursor: pointer;
  pointer-events: auto;
  opacity: 0.55;
  font-size: 12px;
}
.comment-pin:hover,
.comment-pin.active {
  opacity: 1;
}
.comment-pin.resolved {
  border-color: var(--primary);
}
.comment-canvas-popup {
  position: absolute;
  width: min(360px, calc(100% - 16px));
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 24px;
  background: var(--comment-floating-surface);
  color: var(--foreground);
  box-shadow: 0 8px 20px #0003;
  pointer-events: auto;
}
header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 0 8px;
  font-size: 16px;
  line-height: 32px;
}
header strong {
  margin-right: auto;
}
header :deep(button) {
  border: 0;
  border-radius: 50%;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  padding: 0;
  display: grid;
  place-items: center;
  background: var(--comment-floating-control);
  color: var(--foreground);
  cursor: pointer;
}
</style>

<style scoped>
.comment-canvas-popup :deep(.comment-emoji-pop) {bottom:auto;top:calc(100% + 8px)}
.comment-canvas-popup :deep(.comment-card) {background:transparent;border:0;padding:10px 0 14px;margin:0;gap:12px;font-size:14px;line-height:1.5}
.comment-canvas-popup :deep(.comment-card-avatar) {width:34px;height:34px;border:1px solid var(--border);background:var(--comment-floating-control);font-size:14px}
.comment-canvas-popup :deep(.comment-card header) {min-height:26px;gap:5px}
.comment-canvas-popup :deep(.comment-card header strong) {font-size:14px;font-weight:500;max-width:140px}
.comment-canvas-popup :deep(.comment-card time) {font-size:11px}
.comment-canvas-popup :deep(.comment-card-body) {margin:5px 0 8px}
.comment-canvas-popup :deep(.comment-card-reactions button) {padding:2px 9px;min-height:25px;border-radius:8px;font-size:13px;line-height:18px}
.comment-canvas-popup :deep(.comment-card-body svg) {padding:2px;box-sizing:content-box;background:#358cff20;border-radius:5px}
.comment-canvas-popup :deep(.comment-card:not(:last-child)::after) {left:16px;top:48px;bottom:4px;width:4px;border-radius:4px;background:var(--comment-floating-control);}
</style>
