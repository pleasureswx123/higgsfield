<script setup lang="ts">
import { ref } from 'vue'
import { IconCloudUpload } from '@tabler/icons-vue'
import Button from '@/components/ui/Button.vue'
import { useReferenceUploads } from '@/composables/useReferenceUploads'
const props = defineProps<{ projectId: string; folderId: string | null; disabled: boolean }>()
const emit = defineEmits<{ uploaded: [] }>()
const input = ref<HTMLInputElement>()
const { items, running, checking, error, enqueue, pause, retry } = useReferenceUploads(
  props.projectId, () => props.folderId, () => props.disabled, () => emit('uploaded'),
)
function choose(event: Event) {
  const control = event.target as HTMLInputElement
  void enqueue(Array.from(control.files ?? []))
  control.value = ''
}
const stages = { queued: '等待上传', hashing: '计算校验值', uploading: '上传中', verifying: '校验并归档', binding: '绑定素材', done: '已上传，可从下方加入引用', paused: '已暂停', failed: '上传失败' }
defineExpose({ pause })
</script>
<template>
  <section class="reference-upload" aria-label="上传参考素材">
    <div class="reference-upload-heading">
      <Button class="reference-upload-card" variant="outline" :disabled="disabled || checking" aria-label="从电脑上传图片 / 视频" @click="input?.click()"><IconCloudUpload :size="28" /><span>{{ checking ? '核验权限…' : '上传素材' }}</span></Button>
      <span class="muted">保存到{{ folderId ? `当前草稿目录 #${folderId}` : '项目根目录' }}</span>
      <Button v-if="running" variant="ghost" @click="pause">暂停上传</Button>
      <input ref="input" type="file" accept="image/*,video/*" multiple hidden aria-label="上传参考图片或视频" @change="choose" />
    </div>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <ul v-if="items.length" class="reference-upload-list">
      <li v-for="item in items" :key="item.id">
        <span>{{ item.name }}</span><span>{{ stages[item.stage] }}</span>
        <progress :value="item.progress" max="100" :aria-label="`${item.name} 上传进度`" />
        <Button v-if="['failed','paused'].includes(item.stage)" variant="ghost" :disabled="disabled" @click="retry(item)">继续 / 重试</Button>
        <p v-if="item.error" class="project-error">{{ item.error }}</p>
      </li>
    </ul>
  </section>
</template>
<style scoped>
.reference-upload { margin-bottom:16px; }
.reference-upload-card { width:144px; height:144px; display:flex; flex-direction:column; justify-content:center; gap:12px; border:1px dashed var(--border); border-radius:12px; background:var(--surface-raised); }
.reference-upload-heading { display:flex; align-items:center; flex-wrap:wrap; gap:10px; }
.reference-upload-heading .muted { font-size:12px; }
.reference-upload-list { list-style:none; padding:0; }
.reference-upload-list li { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-top:8px; font-size:12px; }
</style>
