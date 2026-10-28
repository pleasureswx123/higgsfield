<script setup lang="ts">
import { ref } from 'vue'
import { usePdfPreview } from '@/composables/usePdfPreview'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ source: Blob }>()
const canvas = ref<HTMLCanvasElement>()
const { page, total, scale, loading, error } = usePdfPreview(() => props.source, canvas)
</script>
<template>
  <section aria-label="PDF文档预览">
    <div class="asset-toolbar">
      <Button variant="outline" :disabled="page <= 1" @click="page--">上一页</Button>
      <span>第 {{ page }} / {{ total }} 页</span>
      <Button variant="outline" :disabled="page >= total" @click="page++">下一页</Button>
      <Button variant="ghost" :disabled="scale <= 0.5" @click="scale = Math.max(0.5, scale - 0.25)">缩小</Button>
      <span>{{ Math.round(scale * 100) }}%</span>
      <Button variant="ghost" :disabled="scale >= 3" @click="scale = Math.min(3, scale + 0.25)">放大</Button>
    </div>
    <p v-if="loading" role="status">正在渲染PDF…</p>
    <p v-if="error" class="project-error" role="alert">{{ error }}；可下载原件后查看。</p>
    <div class="asset-pdf-canvas"><canvas ref="canvas" :aria-label="`PDF第${page}页`" /></div>
  </section>
</template>
<style scoped>
.asset-pdf-canvas { overflow: auto; max-height: 65vh; background: var(--surface); }
canvas { display: block; margin: auto; }
</style>
