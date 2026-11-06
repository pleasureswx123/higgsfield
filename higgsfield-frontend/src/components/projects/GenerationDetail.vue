<script setup lang="ts">
import { useTimestamp, useIntervalFn } from '@vueuse/core'
import { generationFeedback } from '@/utils/generationFeedback'
const feedbackNow = useTimestamp({ scheduler: callback => useIntervalFn(callback, 1000) })
import { Sheet, SheetContent, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { IconRefresh, IconPhoto, IconVideo } from '@tabler/icons-vue'
import GenerationCardMedia from './GenerationCardMedia.vue'
import { computed, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import { useGenerationDetail } from '@/composables/useGenerationDetail'
import { formatProjectDate } from '@/utils/projects'
import GenerationBilling from './GenerationBilling.vue'
import GenerationOutputMetadata from './GenerationOutputMetadata.vue'
import GenerationExecution from './GenerationExecution.vue'

const identity = defineModel<string | undefined>()
function closeDetail() {
  identity.value = undefined
}
function openSource() {
  if (detail.value?.sourceJobId) identity.value = detail.value.sourceJobId
}
const {
  liveState,
  detail,
  input,
  loading,
  inputLoading,
  mediaLoading,
  error,
  inputError,
  mediaError,
  mediaUrl,
  mediaKind,
  refresh,
  readInput,
  media,
  clearMedia,
} = useGenerationDetail(() => identity.value)
const prompt = computed(() =>
  input.value?.prompt.content
    .map((paragraph) =>
      paragraph.content
        .map((node) => (node.type === 'text' ? node.text : `[引用 ${node.referenceKey}]`))
        .join(''),
    )
    .join('\n'),
)
const outputId = ref<string>()
const chosenOutput = computed(() => detail.value?.outputs.find(output => output.id === outputId.value) || detail.value?.outputs[0])
watch(() => [identity.value, chosenOutput.value?.id, chosenOutput.value?.revision, chosenOutput.value?.previewUrl], () => {
  clearMedia()
  if (chosenOutput.value?.previewUrl) void media(chosenOutput.value)
})
watch(identity, () => { outputId.value = undefined; copied.value = '' })
function selectOutput(id: string) {
  outputId.value = id
}
const copied = ref('')
async function copyPrompt() {
  try { await navigator.clipboard.writeText(prompt.value || ''); copied.value = '提示词已复制' }
  catch { copied.value = '复制失败，请选中文字复制' }
}
const taskFeedback = computed(() => detail.value ? generationFeedback(detail.value, feedbackNow.value) : undefined)
const summaryStatus = computed(() => taskFeedback.value?.label || '生成详情')
const previewPending = computed(() => mediaLoading.value || Boolean(chosenOutput.value?.previewUrl && !mediaUrl.value && !mediaError.value))
const archive = {
  not_started: '待归档',
  archiving: '归档中',
  archived: '已归档',
  archive_failed: '归档失败',
  source_expired: '源地址已过期',
  not_applicable: '文本结果',
}
const states = {
  accepted: '等待启动',
  preparing: '准备中',
  submitting: '提交中',
  submission_unknown: '提交异常',
  running: '执行中',
  finished: '编排结束',
  blocked: '已阻塞',
}
const upstream = {
  not_submitted: '未提交',
  queued: '排队中',
  running: '生成中',
  succeeded: '生成成功',
  failed: '生成失败',
  cancelled: '已取消',
  unknown: '结果未确认',
}
const billing = { pending: '待确认', calculated: '已计算', confirmed: '已确认', disputed: '有争议' }
</script>
<template>
  <Sheet :open="!!identity" @update:open="value => { if (!value) closeDetail() }">
    <SheetContent side="right" class="generation-detail-sheet" close-label="关闭生成详情">
      <header class="detail-heading">
        <div><SheetTitle>{{ detail?.model.displayName || '生成任务详情' }}</SheetTitle><SheetDescription>{{ summaryStatus }}<span v-if="detail"> · {{ formatProjectDate(detail.createTime) }}</span></SheetDescription></div>
        <Button variant="ghost" class="detail-refresh" aria-label="刷新详情" title="刷新详情" :disabled="loading" @click="refresh"><IconRefresh :size="17" /></Button>
      </header>
      <div class="detail-scroll">
        <p v-if="loading" role="status" class="muted">正在读取任务详情…</p>
        <p v-if="error" role="alert" class="project-error">{{ error }}</p>
        <section v-if="detail" class="generation-detail">
          <p v-if="taskFeedback && taskFeedback.tone !== 'success'" class="record-diagnostic" role="status">{{ taskFeedback.description }}</p>
          <div class="result-preview">
            <img v-if="mediaUrl && mediaKind === 'image'" :src="mediaUrl" alt="生成结果预览" />
            <video v-else-if="mediaUrl && mediaKind === 'video'" :src="mediaUrl" controls preload="metadata" />
            <pre v-else-if="chosenOutput?.kind === 'text'">{{ chosenOutput.text }}</pre>
            <div v-else class="preview-empty"><IconVideo v-if="detail.kind === 'video'" :size="32" /><IconPhoto v-else :size="32" /><strong>{{ previewPending ? '正在加载结果…' : summaryStatus }}</strong><span>{{ detail.outputsVisibility === 'hidden' ? '当前没有查看输出内容的权限' : previewPending ? '正在读取已归档文件，请稍候。' : chosenOutput ? '暂时无法预览此结果' : '暂无生成结果' }}</span></div>
          </div>
          <p v-if="mediaError" class="project-error" role="alert">{{ mediaError }} <Button v-if="chosenOutput?.previewUrl" variant="ghost" :disabled="mediaLoading" @click="media(chosenOutput)">重新加载</Button></p>
          <div v-if="detail.outputs.length > 1" class="output-selector" aria-label="选择生成结果">
            <div v-for="output in detail.outputs" :key="output.id" class="output-thumbnail" :class="{ selected: chosenOutput?.id === output.id }">
              <GenerationCardMedia v-if="output.kind === 'image' && output.previewUrl" :preview="{ outputId: output.id, revision: output.revision, kind: 'image' }" />
              <IconVideo v-else-if="output.kind === 'video'" :size="22" />
              <button type="button" :aria-pressed="chosenOutput?.id === output.id" :aria-label="`查看结果 ${output.ordinal + 1}`" @click="selectOutput(output.id)"><span>{{ output.ordinal + 1 }}</span></button>
            </div>
          </div>
          <p v-if="detail.diagnostic" role="status" class="record-diagnostic">{{ detail.diagnostic.message }}</p>
          <p v-else-if="summaryStatus === '生成失败'" class="muted">任务已失败，未记录具体原因。</p>
          <p v-else-if="summaryStatus === '异常'" class="muted">本次提交结果尚未确认。</p>
          <div v-if="chosenOutput" class="result-actions">
            <Button v-if="chosenOutput.downloadUrl" :disabled="mediaLoading" @click="media(chosenOutput, true)">下载</Button>
            <span class="muted">{{ archive[chosenOutput.archiveState] }}</span>
          </div>
          <p v-if="chosenOutput?.destinationIssue" class="muted">生成结果已保留，但未能加入原素材目录。</p>
          <p v-if="chosenOutput?.file?.state === 'unavailable'" class="muted">文件当前不可用</p>
          <GenerationOutputMetadata v-if="chosenOutput" :output="chosenOutput" hide-work-status />
          <GenerationExecution v-if="detail.execution" :execution="detail.execution" />
          <details v-if="detail.kind !== 'chat'" class="detail-section" @toggle="event => { if ((event.target as HTMLDetailsElement).open && !input && !inputLoading) readInput() }">
            <summary>提示词与参数</summary>
            <p v-if="inputLoading" role="status">正在读取…</p>
            <p v-if="inputError" role="alert" class="project-error">{{ inputError }} <Button variant="ghost" @click="readInput">重新读取</Button></p>
            <template v-if="input"><pre>{{ prompt || '空提示词' }}</pre><Button variant="ghost" @click="copyPrompt">复制提示词</Button><p v-if="copied" role="status" class="muted">{{ copied }}</p><details class="parameter-details"><summary>生成参数与引用</summary><pre>{{ JSON.stringify(input.parameters, null, 2) }}</pre><p v-for="reference in input.references" :key="`${reference.referenceKey}:${reference.ordinal}`">引用 {{ reference.referenceKey }} · 素材版本 {{ reference.assetVersionId }} · {{ reference.mediaRole }}</p></details></template>
          </details>
          <details v-if="detail.billingVisibility === 'visible'" class="detail-section"><summary>费用与用量</summary><GenerationBilling :detail="detail" /></details>
          <details class="detail-section">
            <summary>任务信息</summary>
            <p class="muted">任务编号 {{ detail.id }} · 更新于 {{ formatProjectDate(detail.updateTime) }}</p>
            <p>{{ states[detail.orchestrationState] }} · {{ upstream[detail.upstreamState] }} · 费用{{ billing[detail.billingState] }}</p>
            <p class="muted">{{ { connecting: '正在连接实时更新…', live: '实时更新已连接', reconnecting: '连接中断，正在重连', stopped: '实时更新已停止' }[liveState] }}</p>
            <p v-if="detail.diagnostic" class="muted">诊断代码：{{ detail.diagnostic.code }}</p>
            <Button v-if="detail.sourceJobId" variant="ghost" @click="openSource">查看来源任务</Button>
          </details>
        </section>
      </div>
    </SheetContent>
  </Sheet>
</template>
<style scoped>
:global(.generation-detail-sheet.generation-detail-sheet) { width:min(680px, 100vw); max-width:none; padding:0; display:flex; flex-direction:column; gap:0; background:var(--background); color:var(--foreground); }
:global(.generation-detail-sheet > button) { top:32px; right:20px; width:32px; height:32px; display:grid; place-items:center; border:0; background:transparent; }
.detail-heading { display:flex; align-items:center; justify-content:space-between; padding:24px 56px 20px 24px; border-bottom:1px solid var(--border); }
.detail-heading :deep(h2) { font-size:18px; margin:0 0 6px; }
.detail-heading :deep(p) { font-size:12px; color:var(--muted-foreground); margin:0; }
.detail-refresh { width:32px; padding:0; }
.detail-scroll { flex:1; min-height:0; overflow-y:auto; padding:24px; }
.result-preview { display:flex; align-items:center; justify-content:center; min-height:260px; border-radius:12px; overflow:hidden; background:var(--surface-raised); }
.result-preview img,.result-preview video { display:block; width:100%; max-height:52vh; object-fit:contain; }
.preview-empty { display:flex; flex-direction:column; align-items:center; gap:12px; padding:40px; color:var(--muted-foreground); font-size:12px; }
.preview-empty strong { color:var(--foreground); font-size:14px; }
.record-diagnostic { padding:12px; border:1px solid var(--border); border-radius:8px; font-size:12px; }
.result-actions { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:16px; }
.detail-section { border-top:1px solid var(--border); padding:18px 0; margin-top:12px; font-size:12px; }
summary { cursor:pointer; font-size:13px; font-weight:500; }
.generation-detail pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:320px; overflow:auto; padding:12px; background:var(--surface); border-radius:8px; font-size:12px; line-height:1.7; }
.parameter-details { margin-top:12px; }
.output-selector { display:flex; gap:8px; overflow-x:auto; padding:12px 2px 2px; }
.output-thumbnail { position:relative; display:flex; align-items:center; justify-content:center; flex:0 0 60px; height:60px; border:2px solid transparent; border-radius:8px; overflow:hidden; background:var(--surface-raised); }
.output-thumbnail.selected { border-color:var(--el-color-primary); }
.output-thumbnail :deep(.generation-card-media) { width:100%; height:100%; margin:0; }
.output-thumbnail button { position:absolute; inset:0; border:0; background:transparent; cursor:pointer; }
.output-thumbnail button span { position:absolute; bottom:2px; right:3px; font-size:11px; background:var(--surface); color:var(--foreground); padding:1px 4px; border-radius:4px; }
</style>
