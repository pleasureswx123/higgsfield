<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import type { GenerationSummary } from '@/api/generations'
import { useGenerationCardMedia } from '@/composables/useGenerationCardMedia'
const props = defineProps<{ preview: NonNullable<GenerationSummary['cardPreview']> }>()
const host = ref<HTMLElement>(), visible = ref(false)
const { url, loading, error, load, mediaFailed } = useGenerationCardMedia(() => props.preview, () => visible.value)
function onMediaError(event: Event) {
  mediaFailed((event.currentTarget as HTMLImageElement | HTMLVideoElement).src)
}
let observer: IntersectionObserver | undefined
onMounted(() => {
  if (!host.value) return
  observer = new IntersectionObserver(entries => { visible.value = entries.some(entry => entry.isIntersecting) }, { rootMargin: '120px' })
  observer.observe(host.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>
<template>
  <div ref="host" class="generation-card-media">
    <img v-if="url && preview.kind === 'image'" :key="url" :src="url" alt="任务归档输出预览" @error="onMediaError" />
    <video v-else-if="url" :key="url" :src="url" controls preload="metadata" @error="onMediaError" />
    <span v-else-if="loading" role="status">正在读取授权媒体…</span>
    <button v-else-if="error" type="button" :title="error" @click="load">{{ preview.kind === 'image' ? '缩略图暂不可用，重试' : '预览不可用，重试' }}</button>
    <button v-else-if="preview.kind === 'video'" type="button" @click="load">打开视频预览</button>
    <span v-else>归档图片</span>
  </div>
</template>
<style scoped>
.generation-card-media { display: flex; align-items: center; justify-content: center; aspect-ratio: 16 / 9; overflow: hidden; border-radius: 10px; margin-bottom: 14px; background: var(--surface-raised); color: var(--muted-foreground); }
img, video { width: 100%; height: 100%; object-fit: contain; }
button { color: inherit; background: transparent; border: 0; cursor: pointer; padding: 12px; }
</style>
