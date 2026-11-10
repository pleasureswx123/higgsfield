<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconSparkles, IconInfoCircle, IconChevronDown, IconChevronUp, IconArrowBackUp } from '@tabler/icons-vue'
import type { AssetGenerationInfo, Asset } from '@/api/assets'
import { formatProjectDate } from '@/utils/projects'
import Button from '@/components/ui/Button.vue'
import { useAssetGenerationCopy } from '@/composables/useAssetGenerationCopy'
const props = defineProps<{ info: AssetGenerationInfo; file: Asset['file']; canLoad?: boolean }>()
const restore = useAssetGenerationCopy(() => props.info.jobId)
const expanded = ref(false)
const detailsOpen = ref(true)
const longPrompt = computed(() => props.info.prompt.length > 100 || props.info.prompt.split('\n').length > 5)
const quality = computed(() => ({ low: '低', medium: '中', high: '高', auto: '自动' }[props.info.quality || ''] || props.info.quality))
</script>

<template>
  <div class="generation-info">
    <div class="prompt-heading">
      <h3 class="generation-heading"><IconSparkles :size="16" />提示词</h3>
      <Button v-if="info.jobId && canLoad" class="restore-input" variant="outline" :disabled="restore.loading.value" title="恢复提示词、参考素材和生成参数，仅载入，不生成" @click="restore.load()"><IconArrowBackUp :size="15" />{{ restore.loading.value ? '载入中…' : '载入创作参数' }}</Button>
    </div>
    <p v-if="restore.error.value || restore.copyError.value" role="alert">{{ restore.error.value || restore.copyError.value }}</p>
    <div class="prompt-card">
      <p :class="{ clamped: longPrompt && !expanded }">{{ info.prompt || '未记录提示词' }}</p>
      <button v-if="longPrompt" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
        {{ expanded ? '收起' : '查看全部' }}<IconChevronUp v-if="expanded" :size="15" /><IconChevronDown v-else :size="15" />
      </button>
    </div>
    <button class="generation-heading details-toggle" type="button" :aria-expanded="detailsOpen" @click="detailsOpen = !detailsOpen">
      <IconInfoCircle :size="16" /><span>生成参数</span><IconChevronUp v-if="detailsOpen" :size="16" /><IconChevronDown v-else :size="16" />
    </button>
    <dl v-if="detailsOpen">
      <template v-if="info.jobId"><dt>任务编号</dt><dd>{{ info.jobId }}</dd></template>
      <dt>模型</dt><dd>{{ info.modelName || '未记录' }}</dd>
      <template v-if="info.resolution"><dt>清晰度</dt><dd>{{ info.resolution }}</dd></template>
      <template v-if="quality"><dt>质量</dt><dd>{{ quality }}</dd></template>
      <template v-if="info.aspectRatio"><dt>生成比例</dt><dd>{{ info.aspectRatio }}</dd></template>
      <template v-if="file.width && file.height"><dt>实际尺寸</dt><dd>{{ file.width }} × {{ file.height }}</dd></template>
      <dt>生成时间</dt><dd>{{ formatProjectDate(info.createTime) }}</dd>
    </dl>
  </div>
</template>

<style scoped>
.generation-info { margin-bottom:14px; }
.prompt-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
.prompt-heading .restore-input { display:inline-flex; align-items:center; gap:5px; font-size:12px; padding:4px 8px; min-height:26px; height:auto; color:var(--foreground); background:transparent; border:1px solid var(--border); border-radius:6px; white-space:nowrap; box-shadow:none; }
.prompt-heading .generation-heading { margin:0; }
.prompt-heading .restore-input:hover { background:var(--surface-hover); }
.generation-heading { display:flex; align-items:center; gap:8px; color:var(--muted-foreground); font-size:12px; }
.prompt-card { padding:10px 12px; background:var(--surface-raised); border-radius:12px; }
.prompt-card p { margin:0; color:var(--foreground); font-size:12px; font-weight:400; line-height:1.5; white-space:pre-wrap; overflow-wrap:anywhere; }
.prompt-card p.clamped { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:6; overflow:hidden; mask-image:linear-gradient(to bottom, #000 60%, transparent); }
button { font:inherit; border:0; background:transparent; cursor:pointer; }
button:focus-visible { outline:2px solid var(--focus); outline-offset:3px; border-radius:4px; }
.prompt-card button { display:flex; align-items:center; gap:4px; padding:0; margin-top:8px; color:var(--muted-foreground); font-size:12px; }
.details-toggle { width:100%; padding:0; margin:14px 0 10px; line-height:18px; text-align:left; }
.details-toggle span { flex:1; }
</style>
