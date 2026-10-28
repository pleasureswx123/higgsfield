<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useReferenceThumbnail } from '@/composables/useReferenceThumbnail'
const props = defineProps<{ versionId: string; fill?: boolean; passive?: boolean; alt?: string; allowOriginal?: boolean }>()
const host = ref<HTMLElement>(), visible = ref(false)
const { url, loading, error, load, mediaFailed } = useReferenceThumbnail(() => props.versionId, () => visible.value, () => Boolean(props.allowOriginal))
function onMediaError(event: Event) {
  mediaFailed((event.currentTarget as HTMLImageElement).src)
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
  <span ref="host" class="reference-thumbnail" :class="{ 'thumbnail-fill': fill }">
    <img v-if="url" :key="url" :src="url" :alt="alt || `参考图片版本 ${versionId}`" @error="onMediaError" />
    <span v-else-if="loading" role="status">读取图片…</span>
    <span v-else-if="error && passive" :title="error">预览暂不可用</span>
    <button v-else-if="error" type="button" :title="error" @click="load">缩略图暂不可用，重试</button>
    <span v-else>参考图片</span>
  </span>
</template>
<style scoped>
.reference-thumbnail { display: inline-flex; width: 96px; height: 72px; flex: 0 0 96px; align-items: center; justify-content: center; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--surface-raised); color: var(--muted-foreground); font-size: 12px; }
.reference-thumbnail img { width: 100%; height: 100%; object-fit: contain; }
.reference-thumbnail button { color: inherit; background: transparent; border: 0; cursor: pointer; }
.reference-thumbnail.thumbnail-fill { width:100%; height:100%; flex:1; border:0; border-radius:inherit; }
</style>
