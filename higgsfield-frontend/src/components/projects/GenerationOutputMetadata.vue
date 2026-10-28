<script setup lang="ts">
import type { GenerationOutput } from '@/api/generations'

defineProps<{ output: GenerationOutput }>()
const workStates = { none: '未设置', working: '制作中', review: '待审核', approved: '已通过', rejected: '已拒绝' }
</script>

<template>
  <section class="output-metadata" aria-label="作品工作状态与实际规格">
    <p>作品工作状态：{{ workStates[output.workStatus] || '状态未知' }}</p>
    <dl v-if="output.kind !== 'text'">
      <div><dt>实际宽度</dt><dd>{{ output.actualMetadata?.width != null ? `${output.actualMetadata.width} px` : '未记录' }}</dd></div>
      <div><dt>实际高度</dt><dd>{{ output.actualMetadata?.height != null ? `${output.actualMetadata.height} px` : '未记录' }}</dd></div>
      <div v-if="output.kind === 'video'"><dt>实际时长</dt><dd>{{ output.actualMetadata?.durationSeconds != null ? `${output.actualMetadata.durationSeconds} 秒` : '未记录' }}</dd></div>
      <div><dt>输出格式</dt><dd>{{ output.actualMetadata?.format || '未记录' }}</dd></div>
    </dl>
    <details v-if="output.actualMetadata?.revisedPrompt">
      <summary>供应商修订提示词</summary>
      <pre>{{ output.actualMetadata.revisedPrompt }}</pre>
      <p class="muted">此内容来自输出记录，不替代任务的原始输入快照。</p>
    </details>
  </section>
</template>

<style scoped>
.output-metadata { margin: 12px 0; }
dl { display: flex; flex-wrap: wrap; gap: 12px 24px; }
dl > div { display: flex; gap: 8px; }
dt { color: var(--muted-foreground); }
dd { margin: 0; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; overflow: auto; }
summary { cursor: pointer; }
</style>
