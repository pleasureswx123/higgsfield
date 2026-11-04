<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconSparkles, IconInfoCircle, IconChevronDown, IconChevronUp } from '@tabler/icons-vue'
import type { AssetGenerationInfo, Asset } from '@/api/assets'
import { formatProjectDate } from '@/utils/projects'
const props = defineProps<{ info: AssetGenerationInfo; file: Asset['file'] }>()
const expanded = ref(false)
const detailsOpen = ref(true)
const longPrompt = computed(() => props.info.prompt.length > 100 || props.info.prompt.split('\n').length > 5)
const quality = computed(() => ({ low: '低', medium: '中', high: '高', auto: '自动' }[props.info.quality || ''] || props.info.quality))
</script>

<template>
  <div class="generation-info">
    <h3 class="generation-heading"><IconSparkles :size="16" />提示词</h3>
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
.generation-info { margin-bottom:20px; }
.generation-heading { display:flex; align-items:center; gap:8px; color:var(--muted-foreground); font-size:12px; }
.prompt-card { padding:14px; background:var(--surface-raised); border-radius:12px; }
.prompt-card p { margin:0; color:var(--foreground); font-size:14px; font-weight:500; line-height:1.6; white-space:pre-wrap; overflow-wrap:anywhere; }
.prompt-card p.clamped { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:6; overflow:hidden; mask-image:linear-gradient(to bottom, #000 60%, transparent); }
button { font:inherit; border:0; background:transparent; cursor:pointer; }
button:focus-visible { outline:2px solid var(--focus); outline-offset:3px; border-radius:4px; }
.prompt-card button { display:flex; align-items:center; gap:4px; padding:0; margin-top:12px; color:var(--muted-foreground); font-size:13px; }
.details-toggle { width:100%; padding:0 4px; margin:18px 0 12px; text-align:left; }
.details-toggle span { flex:1; }
</style>
