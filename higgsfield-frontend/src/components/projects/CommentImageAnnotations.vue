<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElSelect, ElOption } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import type { Annotation, CommentTarget } from '@/api/comments'
import { useCommentImage } from '@/composables/useCommentImage'
import { imagePoint, buildAnnotation, type AnnotationPoint } from '@/utils/commentAnnotation'
const props = defineProps<{ target: CommentTarget; disabled?: boolean; readonly?: boolean; visible?: boolean }>()
const annotations = defineModel<Annotation[]>({ required: true })
const image = useCommentImage(() => props.target, () => props.visible !== false)
const { url, loading, error } = image
const picture = ref<HTMLImageElement>(),
  width = ref(0),
  height = ref(0)
const shape = ref<Annotation['shape']>('point'),
  color = ref('#ff4040')
const points = ref<AnnotationPoint[]>([]),
  pointer = ref<number>()
const preview = computed(() =>
  buildAnnotation(shape.value, points.value, color.value, width.value, height.value),
)
const visible = computed(() =>
  preview.value ? [...annotations.value, preview.value] : annotations.value,
)
function cancel() {
  points.value = []
  pointer.value = undefined
}
watch(() => [url.value, props.disabled, props.readonly], cancel)
watch(url, () => { width.value = 0; height.value = 0 })
function loaded() {
  width.value = picture.value?.naturalWidth || 0
  height.value = picture.value?.naturalHeight || 0
}
function location(event: PointerEvent) {
  return picture.value
    ? imagePoint(event.clientX, event.clientY, picture.value.getBoundingClientRect())
    : undefined
}
function start(event: PointerEvent) {
  if (
    props.disabled ||
    props.visible === false ||
    props.readonly ||
    event.button !== 0 ||
    !width.value ||
    annotations.value.length >= 100
  )
    return
  const point = location(event)
  if (!point) return
  pointer.value = event.pointerId
  points.value = [point]
  ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (pointer.value !== event.pointerId) return
  const point = location(event)
  if (!point) return
  points.value =
    shape.value === 'path' ? [...points.value.slice(0, 255), point] : [points.value[0]!, point]
}
function finish(event: PointerEvent) {
  if (pointer.value !== event.pointerId) return
  move(event)
  if (preview.value) annotations.value = [...annotations.value, preview.value]
  cancel()
}
function path(item: Annotation) {
  return ((item.geometry.points as AnnotationPoint[]) || [])
    .map((p) => `${p.x * 1000},${p.y * 1000}`)
    .join(' ')
}
</script>
<template>
  <div class="annotation-panel">
    <Button variant="ghost" :disabled="loading" @click="image.open">{{
      loading ? '正在读取原图…' : '打开固定图片'
    }}</Button>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <template v-if="url">
      <div v-if="!readonly" class="annotation-tools">
        <ElSelect v-model="shape" aria-label="标注形状" :disabled="disabled"
          ><ElOption label="点" value="point" /><ElOption label="矩形" value="rect" /><ElOption
            label="路径"
            value="path"
        /></ElSelect>
        <label>颜色 <input v-model="color" type="color" :disabled="disabled" /></label>
        <Button
          variant="ghost"
          :disabled="disabled || !annotations.length"
          @click="annotations = annotations.slice(0, -1)"
          >移除最后一个</Button
        >
        <Button
          variant="ghost"
          :disabled="disabled || !annotations.length"
          @click="annotations = []"
          >清空标注</Button
        >
      </div>
      <div class="annotation-stage">
        <img
          ref="picture"
          :src="url"
          alt="当前评论绑定的固定图片"
          draggable="false"
          @load="loaded"
        />
        <svg
          v-if="width && height"
          viewBox="0 0 1000 1000"
          preserveAspectRatio="none"
          :class="{ drawing: !readonly && !disabled }"
          role="img"
          aria-label="图片定位标注"
          @pointerdown="start"
          @pointermove="move"
          @pointerup="finish"
          @pointercancel="cancel"
          @lostpointercapture="cancel"
        >
          <g
            v-for="(item, index) in visible"
            :key="index"
            :stroke="item.color"
            fill="none"
            stroke-width="2"
          >
            <circle
              v-if="item.shape === 'point'"
              :cx="Number(item.geometry.x) * 1000"
              :cy="Number(item.geometry.y) * 1000"
              r="7"
              vector-effect="non-scaling-stroke"
            />
            <rect
              v-else-if="item.shape === 'rect'"
              :x="Number(item.geometry.x) * 1000"
              :y="Number(item.geometry.y) * 1000"
              :width="Number(item.geometry.width) * 1000"
              :height="Number(item.geometry.height) * 1000"
              vector-effect="non-scaling-stroke"
            />
            <polyline v-else :points="path(item)" vector-effect="non-scaling-stroke" />
          </g>
        </svg>
      </div>
      <p class="muted">
        {{ annotations.length }}/100 个标注 · 原图 {{ width }} × {{ height
        }}<span v-if="!readonly"> · 点击添加点，拖动绘制矩形或路径。</span>
      </p>
    </template>
  </div>
</template>
<style scoped>
.annotation-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0;
}
.annotation-tools .el-select {
  width: 110px;
}
.annotation-stage {
  position: relative;
  width: 100%;
}
.annotation-stage img {
  display: block;
  width: 100%;
  height: auto;
}
.annotation-stage svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.annotation-stage svg.drawing {
  touch-action: none;
  cursor: crosshair;
}
</style>
