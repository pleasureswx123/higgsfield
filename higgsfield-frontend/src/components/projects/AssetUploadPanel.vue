<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconCheck, IconChevronUp, IconChevronDown, IconX } from '@tabler/icons-vue'
import type { UploadItem } from '@/composables/useAssetUploads'
const props = defineProps<{ items: UploadItem[]; running: boolean; canUpload: boolean }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ pause: []; pauseItem: [item: UploadItem]; retry: [item: UploadItem]; clear: [] }>()
const collapsed = ref(false)
const completed = computed(() => props.items.filter(item => item.stage === 'done').length)
const transferred = computed(() => props.items.reduce((sum, item) => sum + item.uploadedBytes, 0))
const total = computed(() => props.items.reduce((sum, item) => sum + item.file.size, 0))
const stages = { queued: '等待上传', hashing: '准备中', uploading: '上传中', verifying: '校验并归档', binding: '保存素材', done: '已上传', paused: '已暂停', failed: '上传失败' }
const active = (item: UploadItem) => ['hashing', 'uploading', 'verifying', 'binding'].includes(item.stage)
function bytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <aside v-if="open" class="upload-popover" aria-label="上传队列">
    <header>
      <button type="button" class="upload-panel-title" :aria-expanded="!collapsed" @click="collapsed = !collapsed">
        <IconChevronDown v-if="collapsed" :size="16" /><IconChevronUp v-else :size="16" />上传
      </button>
      <button type="button" class="upload-panel-close" aria-label="关闭上传队列" @click="open = false"><IconX :size="16" /></button>
    </header>
    <div v-show="!collapsed" class="upload-panel-list">
      <p class="upload-destination">上传至各文件选择时所在目录</p>
      <div v-for="item in items" :key="item.id" class="upload-panel-item">
        <span v-if="item.stage === 'done'" class="upload-complete"><IconCheck :size="12" /></span>
        <span v-else class="upload-progress-ring" :class="{ spinning: active(item), failed: item.stage === 'failed' }" :style="{ '--progress': `${item.stage === 'uploading' ? item.progress : 0}%` }" :aria-label="`${item.name} ${stages[item.stage]}`"></span>
        <div class="upload-file-copy">
          <strong :title="item.name">{{ item.name }}</strong>
          <small>{{ stages[item.stage] }}<template v-if="item.stage === 'uploading'"> {{ bytes(item.uploadedBytes) }} / {{ bytes(item.file.size) }}</template></small>
          <small v-if="item.error && item.stage === 'failed'" class="upload-file-error" role="alert">{{ item.error }}</small>
        </div>
        <button v-if="active(item) || item.stage === 'queued'" type="button" @click="emit('pauseItem', item)">暂停</button>
        <button v-else-if="canUpload && ['paused', 'failed'].includes(item.stage)" type="button" @click="emit('retry', item)">{{ item.stage === 'failed' ? '重试' : '继续' }}</button>
      </div>
    </div>
    <footer role="status">
      <span v-if="completed === items.length" class="upload-complete"><IconCheck :size="12" /></span>
      <span v-else class="upload-progress-ring" :class="{ spinning: running }"></span>
      <div><strong>{{ completed === items.length ? '上传完成' : running ? '正在上传' : '上传已暂停或失败' }}</strong><small>{{ completed }} / {{ items.length }} 已完成<span v-if="running"> · {{ bytes(transferred) }} / {{ bytes(total) }}</span></small></div>
      <button v-if="running" type="button" @click="emit('pause')">全部暂停</button>
      <button v-else-if="completed" type="button" @click="emit('clear')">清除已完成</button>
    </footer>
  </aside>
</template>

<style scoped>
.upload-popover { position:fixed; z-index:45; top:68px; right:24px; width:min(360px, calc(100vw - 32px)); border:1px solid var(--border); border-radius:20px; background:var(--surface-raised); color:var(--foreground); box-shadow:0 12px 32px #0003; padding:5px; font-size:12px; }
.upload-popover header { display:flex; align-items:center; justify-content:space-between; padding:6px 8px; }
.upload-popover button { border:0; cursor:pointer; color:inherit; background:var(--surface-hover); border-radius:7px; padding:5px 8px; font-size:12px; white-space:nowrap; }
.upload-popover .upload-panel-title { display:flex; gap:8px; align-items:center; font-weight:650; font-size:14px; background:transparent; }
.upload-popover .upload-panel-close { display:grid; place-items:center; border-radius:50%; width:30px; height:30px; padding:0; }
.upload-panel-list { background:var(--surface-hover); border-radius:14px; padding:12px; max-height:min(360px, 55dvh); overflow:auto; }
.upload-destination { margin:0 0 12px; color:var(--muted-foreground); }
.upload-panel-item { display:flex; align-items:center; gap:12px; padding:6px 2px; }
.upload-file-copy { flex:1; min-width:0; }
.upload-file-copy strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.upload-popover small { display:block; color:var(--muted-foreground); margin-top:4px; font-size:12px; }
.upload-popover .upload-file-error { color:var(--destructive, #ef4444); overflow-wrap:anywhere; }
.upload-complete { display:grid; place-items:center; width:17px; height:17px; flex:0 0 17px; border-radius:50%; background:var(--primary); color:var(--primary-foreground); }
.upload-progress-ring { display:block; flex:0 0 17px; width:17px; height:17px; border-radius:50%; background:conic-gradient(var(--primary) var(--progress, 20%), var(--border) 0); mask:radial-gradient(circle, transparent 6px, #000 6.5px); }
.upload-progress-ring.spinning { animation:upload-spin 1s linear infinite; }
.upload-progress-ring.failed { background:var(--destructive, #ef4444); }
.upload-popover footer { display:flex; align-items:center; gap:10px; padding:12px; }
.upload-popover footer > div { flex:1; min-width:0; }
.upload-popover footer strong { font-size:12px; }
@keyframes upload-spin { to { transform:rotate(360deg); } }
</style>
