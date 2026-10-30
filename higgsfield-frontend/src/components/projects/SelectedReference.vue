<script setup lang="ts">
import { IconX, IconMaximize, IconPencil } from '@tabler/icons-vue'
import { ElDialog } from 'element-plus'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { useReferencePreview } from '@/composables/useReferencePreview'
import type { DraftReference } from '@/api/creation'
import ReferenceThumbnail from './ReferenceThumbnail.vue'
const props = defineProps<{ item: DraftReference; disabled: boolean; protected: boolean; video?: boolean; label?: string }>()
const emit = defineEmits<{ remove: []; edit: [anchor: HTMLElement] }>()
const preview = useReferencePreview(() => !props.disabled)
function enlarge() {
  void preview.show({ displayName: '参考图片预览', assetVersionIds: [props.item.assetVersionId], allowedMediaRoles: ['reference_image'] })
}
function edit(event: MouseEvent) {
  emit('edit', (event.currentTarget as HTMLElement).closest('.composer-main-panel') as HTMLElement)
}
</script>
<template>
  <div class="selected-reference" :class="{ 'selected-video': video }" :aria-label="video ? '已选参考视频' : '已选参考图片'">
    <ReferenceThumbnail :version-id="item.assetVersionId" fill passive :allow-original="!video" />
    <span v-if="video" class="video-caption">{{ label || '参考视频' }}</span>
    <button v-if="video" class="reference-edit" type="button" :disabled="disabled" aria-label="编辑参考视频" title="选择参考视频" @click="edit"><IconPencil :size="13" /></button>
    <button v-else class="reference-enlarge" type="button" :disabled="disabled" :aria-label="`放大参考图片 ${item.assetVersionId}`" title="放大预览" @click="enlarge"><IconMaximize :size="19" /></button>
    <button class="reference-remove" type="button" :disabled="disabled || protected" :aria-label="`移除${video ? '视频' : '图片'}引用 ${item.assetVersionId}`" :title="protected ? '提示词仍提及此引用，请先编辑提示词' : '移除引用'" @click="$emit('remove')"><IconX :size="12" /></button>
  </div>
  <ElDialog :model-value="Boolean(preview.candidate.value)" width="min(1000px, 94vw)" append-to-body :before-close="preview.close" :close-on-click-modal="false">
    <template #header="{ titleId, titleClass }"><DialogHeading :title-id="titleId" :title-class="titleClass" title="参考图片预览" /></template>
    <p v-if="preview.loading.value" role="status">正在读取预览…</p>
    <p v-if="preview.error.value" role="alert">{{ preview.error.value }}</p>
    <img v-if="preview.url.value" :src="preview.url.value" alt="参考图片预览" class="selected-reference-preview" />
  </ElDialog>
</template>
<style scoped>
.selected-reference { position:relative; flex:0 0 48px; width:48px; height:48px; border-radius:7px; background:var(--surface-hover); }
.selected-reference :deep(.reference-thumbnail img) { object-fit:cover; }
.selected-video { flex-basis:80px; width:80px; height:80px; overflow:hidden; border:0; border-radius:12px; box-shadow:0 2px 5px #0005; }
.video-caption { position:absolute; inset:0; display:flex; align-items:flex-end; padding:7px 6px; background:linear-gradient(transparent 30%,#000b); color:white; font-size:11px; font-weight:800; line-height:1.15; pointer-events:none; }
.selected-reference button { position:absolute; right:2px; top:2px; display:grid; place-items:center; width:18px; height:18px; padding:0; border:0; border-radius:50%; background:var(--surface-raised); color:var(--foreground); cursor:pointer; }
.selected-reference button { opacity:0; transition:opacity .15s; }
.selected-reference:hover button,.selected-reference:focus-within button { opacity:1; }
.selected-reference:hover button:disabled,.selected-reference:focus-within button:disabled { opacity:.45; cursor:not-allowed; }
.selected-reference .reference-edit { left:3px; right:auto; }
.selected-reference .reference-enlarge { inset:0; width:100%; height:100%; border-radius:inherit; background:#0005; color:white; }
.selected-reference .reference-remove { z-index:1; }
.selected-reference-preview { display:block; width:100%; height:65vh; object-fit:contain; }
@media (hover:none) { .selected-reference button { opacity:1; } }
.selected-reference button:focus-visible { outline:2px solid var(--focus); }
.play-mark { position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); color:white; filter:drop-shadow(0 1px 3px #000); pointer-events:none; }
</style>
