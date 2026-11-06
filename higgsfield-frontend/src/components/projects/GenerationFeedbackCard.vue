<script setup lang="ts">
import { computed } from 'vue'
import { useTimestamp, useIntervalFn } from '@vueuse/core'
import { IconLoader2, IconCircleCheck, IconAlertCircle, IconClock } from '@tabler/icons-vue'
import type { GenerationSummary } from '@/api/generations'
import { generationFeedback, generationElapsed, generationStage } from '@/utils/generationFeedback'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ row?: GenerationSummary; awaiting: boolean; error: string; loading: boolean }>()
const emit = defineEmits<{ refresh: []; detail: [id: string] }>()
const now = useTimestamp({ scheduler: callback => useIntervalFn(callback, 1000) })
const feedback = computed(() => props.row ? generationFeedback(props.row, now.value) : undefined)
const elapsed = computed(() => props.row ? generationElapsed(props.row, now.value) : '')
const stage = computed(() => props.row ? generationStage(props.row) : 0)
const steps = ['任务已提交', '准备素材', '生成', '保存结果']
const completed = computed(() => feedback.value?.tone === 'success')
const resultLabel = computed(() => props.row?.kind === 'image' ? '查看图片' : props.row?.kind === 'video' ? '查看视频' : '查看结果')
</script>

<template>
  <section class="generation-feedback" :data-tone="feedback?.tone" aria-label="本次创作进度">
    <div class="feedback-main">
      <IconLoader2 v-if="feedback?.spinning || awaiting" class="feedback-spinner" :size="18" aria-hidden="true" />
      <IconCircleCheck v-else-if="completed" :size="18" aria-hidden="true" />
      <IconAlertCircle v-else-if="feedback?.tone === 'warning' || feedback?.tone === 'danger'" :size="18" aria-hidden="true" />
      <IconClock v-else :size="18" aria-hidden="true" />
      <div class="feedback-copy">
        <div class="feedback-heading"><strong role="status">{{ feedback?.label || '任务已提交' }}</strong><span v-if="elapsed" class="elapsed">{{ elapsed }}</span></div>
        <p>{{ feedback?.description || '正在读取执行状态，无需重复提交。' }}</p>
        <p v-if="error" class="feedback-error" role="status">状态更新暂时中断，以上是上次结果；正在尝试重新连接。生成任务不会因此取消。</p>
        <template v-if="stage >= 0 && !completed">
          <ol class="feedback-steps" aria-label="生成阶段"><li v-for="(step, index) in steps" :key="step" :data-reached="index <= stage" :aria-current="index === stage ? 'step' : undefined">{{ step }}</li></ol>
          <p class="feedback-hint">可以继续创作，离开页面不影响生成；完成后会在平台内通知你。</p>
        </template>
      </div>
    </div>
    <div class="feedback-actions">
      <Button v-if="row" :variant="completed ? 'default' : 'outline'" @click="emit('detail', row.id)">{{ completed ? resultLabel : '查看详情' }}</Button>
      <Button v-if="!completed || error" variant="ghost" :disabled="loading" @click="emit('refresh')">{{ loading ? '更新中…' : error ? '重新连接' : '刷新状态' }}</Button>
    </div>
  </section>
</template>

<style scoped>
.generation-feedback { display:flex; align-items:center; gap:16px; padding:14px 16px; margin-bottom:10px; border:1px solid var(--border); border-radius:12px; background:var(--surface); color:var(--foreground); font-size:12px; }
.feedback-main { display:flex; align-items:flex-start; gap:10px; flex:1; min-width:0; }
.feedback-main > svg { flex-shrink:0; margin-top:2px; color:var(--muted-foreground); }
.feedback-copy { flex:1; min-width:0; }
.feedback-heading { display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }
.feedback-heading strong { font-size:13px; }.elapsed { color:var(--muted-foreground); font-variant-numeric:tabular-nums; }
.generation-feedback p { margin:5px 0 0; line-height:1.6; color:var(--muted-foreground); }
.feedback-steps { display:flex; flex-wrap:wrap; gap:6px 12px; list-style:none; padding:0; margin:9px 0 0; color:var(--muted-foreground); }
.feedback-steps li::before { content:'·'; margin-right:6px; }.feedback-steps li[data-reached="true"] { color:var(--foreground); }.feedback-steps li[aria-current="step"] { font-weight:700; }
.feedback-actions { display:flex; align-items:center; gap:6px; flex-shrink:0; }
.generation-feedback[data-tone="warning"] .feedback-main > svg,.generation-feedback .feedback-error { color:var(--el-color-warning); }
.generation-feedback[data-tone="danger"] .feedback-main > svg { color:var(--el-color-danger); }
.generation-feedback[data-tone="success"] .feedback-main > svg { color:var(--el-color-success); }
.feedback-spinner { animation:feedback-spin 1s linear infinite; } @keyframes feedback-spin { to { transform:rotate(360deg); } }
@media(prefers-reduced-motion:reduce) { .feedback-spinner { animation:none; } }
@media(max-width:640px) { .generation-feedback { flex-direction:column; align-items:stretch; gap:10px; }.feedback-actions { justify-content:flex-end; } }
</style>
