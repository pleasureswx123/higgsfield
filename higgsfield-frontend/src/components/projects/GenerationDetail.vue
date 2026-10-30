<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { computed, ref, watch, onDeactivated } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ElDialog, ElForm, ElFormItem, ElInput, type FormInstance } from 'element-plus'
import { useGenerationArchiveRetry } from '@/composables/useGenerationArchiveRetry'
import { useGenerationCancel } from '@/composables/useGenerationCancel'
import { useGenerationCopy } from '@/composables/useGenerationCopy'
import Button from '@/components/ui/Button.vue'
import { useGenerationDetail } from '@/composables/useGenerationDetail'
import { formatProjectDate } from '@/utils/projects'
import GenerationBilling from './GenerationBilling.vue'
import GenerationGuidance from './GenerationGuidance.vue'
import GenerationOutputMetadata from './GenerationOutputMetadata.vue'
import OutputToAssetDialog from './OutputToAssetDialog.vue'
import OutputToElementDialog from './OutputToElementDialog.vue'
import OutputStatusDialog from './OutputStatusDialog.vue'

import MediaComments from './MediaComments.vue'
const toAsset = ref<string>()

const toElement = ref<string>()
const statusOutput = ref<string>()
const commentOutput = ref<string>()
const comments = ref<InstanceType<typeof MediaComments>[]>([])
async function mayLeaveComments() {
  for (const panel of comments.value) if (!(await panel.confirmLeave())) return false
  return true
}
async function selectCommentOutput(id: string) {
  if (commentOutput.value === id) return
  if (await mayLeaveComments()) commentOutput.value = id
}
async function closeDetail() {
  if (!actionPending.value && (await mayLeaveComments())) identity.value = undefined
}
async function openSource() {
  const id = detail.value?.sourceJobId
  if (id && !actionPending.value && (await mayLeaveComments()) &&
      detail.value?.sourceJobId === id && !actionPending.value) identity.value = id
}
const identity = defineModel<string | undefined>()
watch(
  () => [identity.value, useAuthStore().token],
  () => {
    toAsset.value = undefined
    toElement.value = undefined
    statusOutput.value = undefined
    commentOutput.value = undefined
  },
)
onDeactivated(() => {
  toAsset.value = undefined
    statusOutput.value = undefined
})
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
const elementDestination = computed(() => detail.value?.elementDestination || undefined)
const copyDraft = useGenerationCopy(() => detail.value)
async function copyInput() {
  if (!(await mayLeaveComments())) return
  if (await copyDraft.copy()) identity.value = undefined
}
const cancel = useGenerationCancel(
  () => identity.value,
  () => detail.value,
  refresh,
)
const archiveRetry = useGenerationArchiveRetry(
  () => identity.value,
  () => detail.value,
  refresh,
)
const actionPending = computed(
  () => cancel.pending.value || archiveRetry.pending.value || copyDraft.pending.value || !!toAsset.value || !!toElement.value || !!statusOutput.value,
)
const cancelForm = ref<FormInstance>()
const cancelModel = computed(() => ({ reason: cancel.reason.value }))
async function submitCancel() {
  if (!(await cancelForm.value?.validate().catch(() => false))) return
  await cancel.submit()
}
const prompt = computed(() =>
  input.value?.prompt.content
    .map((paragraph) =>
      paragraph.content
        .map((node) => (node.type === 'text' ? node.text : `[引用 ${node.referenceKey}]`))
        .join(''),
    )
    .join('\n'),
)
const archive = {
  not_started: '待归档',
  archiving: '归档中',
  archived: '已归档',
  archive_failed: '归档失败',
  source_expired: '源地址已过期',
  not_applicable: '文本结果',
}
const states = {
  accepted: '已受理',
  preparing: '准备中',
  submitting: '提交中',
  submission_unknown: '提交待核查',
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
  unknown: '待核查',
}
const billing = { pending: '待确认', calculated: '已计算', confirmed: '已确认', disputed: '有争议' }
</script>
<template>
  <ElDialog
    :model-value="!!identity"
    title="生成任务详情"
    width="min(900px, 94vw)"
    destroy-on-close
    :close-on-click-modal="!actionPending"
    :close-on-press-escape="!actionPending"
    :show-close="!actionPending"
    :before-close="closeDetail"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="生成任务详情" />
    </template>
    <p class="muted" role="status">
      {{
        {
          connecting: '正在连接实时更新…',
          live: '实时更新已连接',
          reconnecting: '连接中断，正在自动重连；可手动刷新。',
          stopped: '实时更新已停止',
        }[liveState]
      }}
    </p>
    <p v-if="loading" role="status">正在读取任务详情…</p>
    <p v-if="error" role="alert" class="project-error">{{ error }}</p>
    <Button variant="ghost" :disabled="loading || actionPending" @click="refresh">刷新详情</Button>
    <section v-if="detail" class="generation-detail">
      <h2>{{ detail.model.displayName }} · {{ detail.id }}</h2>
      <p class="muted">更新于 {{ formatProjectDate(detail.updateTime) }}</p>
      <Button v-if="detail.sourceJobId" variant="ghost" :disabled="actionPending" @click="openSource">
        查看来源任务 #{{ detail.sourceJobId }}
      </Button>
      <p v-if="detail.cancelState === 'confirmed'" role="status">取消已确认</p>
      <ElForm
        v-if="detail.allowedActions.includes('generation:cancel') || cancel.retryable.value"
        ref="cancelForm"
        :model="cancelModel"
        label-position="top"
        @submit.prevent
      >
        <ElFormItem
          label="取消原因"
          prop="reason"
          :rules="[
            { required: true, whitespace: true, message: '请填写取消原因', trigger: 'blur' },
          ]"
        >
          <ElInput
            v-model="cancel.reason.value"
            type="textarea"
            maxlength="4000"
            show-word-limit
            :disabled="cancel.pending.value || cancel.retryable.value"
          />
        </ElFormItem>
        <Button variant="ghost" :disabled="cancel.pending.value" @click="submitCancel">
          {{
            cancel.pending.value
              ? '正在取消…'
              : cancel.retryable.value
                ? '重试确认取消结果'
                : '取消未提交任务'
          }}
        </Button>
      </ElForm>
      <p v-if="cancel.error.value" role="alert" class="project-error">{{ cancel.error.value }}</p>
      <p>
        {{ states[detail.orchestrationState] }} · {{ upstream[detail.upstreamState] }} · 费用{{
          billing[detail.billingState]
        }}
      </p>
      <GenerationBilling :detail="detail" />
      <GenerationGuidance :detail="detail" />
      <p v-if="detail.outputsVisibility === 'hidden'">当前没有查看输出内容的权限。</p>
      <p v-else-if="!detail.outputs.length" class="muted">暂无可见输出。</p>
      <p v-if="archiveRetry.error.value" role="alert" class="project-error">
        {{ archiveRetry.error.value }}
      </p>
      <Button
        v-if="archiveRetry.retryable.value"
        variant="ghost"
        :disabled="actionPending"
        @click="archiveRetry.submit()"
        >重试确认归档调度结果</Button
      >
      <article v-for="output in detail.outputs" :key="output.id" class="generation-output">
        <strong>输出 {{ output.ordinal + 1 }} · {{ archive[output.archiveState] }}</strong>
        <GenerationOutputMetadata :output="output" />
        <Button v-if="output.allowedActions.includes('output:work-status')" variant="ghost" :disabled="actionPending" @click="statusOutput = output.id">修改工作状态</Button>
        <Button
          v-if="output.allowedActions.includes('output:archive')"
          variant="ghost"
          :disabled="actionPending || archiveRetry.retryable.value"
          @click="archiveRetry.submit(output.id)"
          >重试此输出归档</Button
        >
        <pre v-if="output.kind === 'text'">{{ output.text }}</pre>
        <div class="generation-output-actions">
          <Button
            v-if="
              elementDestination?.projectId === detail.projectId &&
              output.kind === 'image' &&
              output.archiveState === 'archived' &&
              output.file?.state === 'ready' &&
              output.allowedActions.includes('output:to-asset')
            "
            variant="ghost"
            :disabled="actionPending"
            @click="toElement = output.id"
            >加入目标元素</Button
          >
          <Button
            v-if="output.allowedActions.includes('output:to-asset')"
            variant="ghost"
            :disabled="actionPending"
            @click="toAsset = output.id"
            >转为素材</Button
          >

          <Button
            v-if="output.previewUrl"
            variant="ghost"
            :disabled="mediaLoading"
            @click="media(output)"
            >预览</Button
          >
          <Button
            v-if="output.downloadUrl"
            variant="ghost"
            :disabled="mediaLoading"
            @click="media(output, true)"
            >下载</Button
          >
          <span v-if="output.file?.state === 'unavailable'">归档文件当前不可用</span>
        </div>
        <Button variant="ghost" @click="selectCommentOutput(output.id)">查看作品评论</Button>
        <MediaComments
          ref="comments"
          v-if="commentOutput === output.id"
          :key="output.id"
          :target="{ outputId: output.id }"
          :media-kind="output.kind"
        />
      </article>
      <p v-if="mediaLoading" role="status">正在读取授权媒体…</p>
      <p v-if="mediaError" role="alert" class="project-error">{{ mediaError }}</p>
      <div v-if="mediaUrl" class="generation-media">
        <Button variant="ghost" @click="clearMedia">关闭预览</Button>
        <img v-if="mediaKind === 'image'" :src="mediaUrl" alt="生成结果预览" />
        <video v-else-if="mediaKind === 'video'" :src="mediaUrl" controls preload="metadata" />
      </div>
      <Button
        v-if="detail.kind !== 'chat'"
        variant="ghost"
        :disabled="inputLoading"
        @click="readInput"
        >{{ inputLoading ? '读取中…' : '查看原始输入' }}</Button
      >
      <p v-if="inputError" role="alert" class="project-error">{{ inputError }}</p>
      <Button
        v-if="detail.allowedActions.includes('generation:copy-input') || copyDraft.retryable.value"
        variant="ghost"
        :disabled="actionPending"
        @click="copyInput"
      >{{ copyDraft.pending.value ? '正在复制…' : copyDraft.retryable.value ? '重试保存或打开草稿' : '复制输入为新草稿（不生成）' }}</Button>
      <p v-if="copyDraft.error.value" role="alert" class="project-error">{{ copyDraft.error.value }}</p>
      <section v-if="input">
        <h3>原始提示词</h3>
        <pre>{{ prompt || '空提示词' }}</pre>
        <h3>生成参数</h3>
        <pre>{{ JSON.stringify(input.parameters, null, 2) }}</pre>
        <h3 v-if="input.references.length">固定引用</h3>
        <p
          v-for="reference in input.references"
          :key="`${reference.referenceKey}:${reference.ordinal}`"
        >
          引用 {{ reference.referenceKey }} · 素材版本 {{ reference.assetVersionId }} ·
          {{ reference.mediaRole }}
        </p>
      </section>
    </section>
  </ElDialog>
  <OutputStatusDialog v-if="statusOutput && detail" :key="statusOutput"
    :output="detail.outputs.find(output => output.id === statusOutput)"
    @close="statusOutput = undefined" @saved="refresh" />
  <OutputToAssetDialog
    v-if="toAsset && detail"
    :key="toAsset"
    :output-id="toAsset"
    :project-id="detail.projectId"
    @close="toAsset = undefined"
  />
  <OutputToElementDialog
    v-if="toElement && detail && elementDestination"
    :key="toElement"
    :output-id="toElement"
    :job-id="detail.id"
    :target="elementDestination"
    @close="toElement = undefined"
  />
</template>
<style scoped>
.generation-output {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin: 12px 0;
  background: var(--surface);
}
.generation-output-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.generation-detail pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 360px;
  overflow: auto;
  background: var(--surface);
  padding: 12px;
  border-radius: 8px;
}
.generation-media img,
.generation-media video {
  display: block;
  max-width: 100%;
  max-height: 60vh;
  margin: 12px auto;
}
</style>
