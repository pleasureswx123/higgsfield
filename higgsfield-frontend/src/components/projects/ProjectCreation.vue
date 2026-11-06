<script setup lang="ts">
import { generationSubmissionFeedback } from '@/utils/generationFeedback'
import GenerationFeedbackCard from './GenerationFeedbackCard.vue'
import StudioPagination from '@/components/ui/StudioPagination.vue'
import { IconX, IconHistory } from '@tabler/icons-vue'
import { ElForm, ElFormItem, ElMessage, } from 'element-plus'

import type { Asset } from '@/api/assets'
import { selectCandidate } from '@/utils/draftReferences'
import CreationComposer from '@/components/creation/CreationComposer.vue'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import { useElementUse } from '@/composables/useElementUse'
import { useElementGenerationTarget } from '@/composables/useElementGenerationTarget'
import { useCreationDraft } from '@/composables/useCreationDraft'
import DraftReferences from './DraftReferences.vue'
import SelectedReference from './SelectedReference.vue'
import type { DraftReference } from '@/api/creation'
import ComposerPrompt from '@/components/creation/ComposerPrompt.vue'
import { removePromptReference } from '@/utils/promptEditorDocument'
import GenerationDetail from './GenerationDetail.vue'
import type { GenerationActivityState } from '@/composables/useGenerationActivity'
import { useCreationProgress } from '@/composables/useCreationProgress'
import { useGenerationSubmit } from '@/composables/useGenerationSubmit'
const props = defineProps<{ projectId: string; activity: GenerationActivityState; initialPrompt?: string; initialKind?: 'image' | 'video'; dock?: boolean }>()
const emit = defineEmits<{ assetsChanged: [folders: (string | null)[]] }>()
const route = useRoute()
const draftsOpen = ref(false)
const referencePicker = ref<InstanceType<typeof DraftReferences>>()
const pickerOpen = ref(false)
const promptEditor = ref<InstanceType<typeof ComposerPrompt>>()
const {
  body,
  kind,
  promptDocument,
  prompt,
  models,
  selected,
  parameters,
  loading,
  saving,
  autoSaveError,
  uncertain: draftUncertain,
  locked: draftLocked,
  editingLocked,
  error,
  notice,
  formRef,
  form,
  dirty,
  draft,
  drafts,
  draftPage,
  draftTotal,
  draftsLoading,
  opening,
  protectedReferenceKeys,
  missingModel,
  references,
  loadDrafts,
  openDraft,
  choose,
  setParameter,
  changeKind,
  save,
} = useCreationDraft(props.projectId, () => {
  const folder = route.query.folder
  return route.params.id === props.projectId && typeof folder === 'string' && /^[1-9]\d*$/.test(folder)
    ? folder
    : null
}, { prompt: props.initialPrompt, kind: props.initialKind, autoSave: true, pauseAutoSave: () => pickerOpen.value })
watch(draftsOpen, open => { if (open) void loadDrafts() })
const imageReferences = computed(() => references.value.filter(item => item.mediaRole !== 'reference_video').sort((a, b) => Number(Boolean(a.elementRevisionId)) - Number(Boolean(b.elementRevisionId))))
const videoReference = computed(() => references.value.find(item => item.mediaRole === 'reference_video'))
function removeSelected(item: DraftReference) {
  if (draftLocked.value || opening.value || generation.locked.value) return
  const remaining = references.value.filter(value => value.referenceKey !== item.referenceKey).map((value, ordinal) => ({ ...value, ordinal }))
  promptDocument.value = removePromptReference(promptDocument.value, remaining, item.referenceKey)
  references.value = remaining
}
const elementTarget = useElementGenerationTarget(props.projectId)
watch(
  () => [route.params.id, route.query.draft],
  () => {
    const id = route.query.draft
    if (
      route.params.id === props.projectId &&
      typeof id === 'string' &&
      /^[1-9]\d*$/.test(id) &&
      draft.value?.id !== id
    )
      void openDraft(id)
  },
  { immediate: true },
)
const generation = useGenerationSubmit(() =>
  selected.value &&
  body.value.modelVersionId &&
  (!elementTarget.requested.value || (elementTarget.target.value && kind.value === 'image'))
    ? {
        projectId: props.projectId,
        kind: kind.value,
        modelVersionId: body.value.modelVersionId,
        prompt: body.value.prompt,
        parameters: body.value.parameters,
        references: references.value,
        folderId: body.value.folderId,
        sourceJobId: body.value.sourceJobId,
        ...(elementTarget.target.value ? { targetElementId: elementTarget.target.value.id } : {}),
        ...(!dirty.value && draft.value
          ? { draftId: draft.value.id, draftRevision: draft.value.revision }
          : {}),
      }
    : undefined,
  () => props.projectId,
)
const elementUse = useElementUse(
  props.projectId,
  () => ({
    prompt: promptDocument.value,
    references: references.value,
    model: selected.value,
    kind: kind.value,
  }),
  () => draftLocked.value || opening.value || generation.locked.value,
  (value) => {
    promptDocument.value = value.prompt
    references.value = value.references
  },
)
function useAsset(asset: Asset, targetKind: 'image' | 'video') {
  if (draftLocked.value || opening.value || generation.locked.value || asset.mediaType === 'document') return
  changeKind(targetKind)
  if (kind.value !== targetKind) return
  const role = asset.mediaType === 'video' ? 'reference_video' : 'reference_image'
  try {
    references.value = selectCandidate(references.value, { kind: 'asset', id: asset.id, projectId: props.projectId, displayName: asset.name, assetVersionIds: [asset.currentVersionId], allowedMediaRoles: [role] }, role, selected.value, protectedReferenceKeys.value)
    ElMessage.success(asset.mediaType === 'video' ? '已添加参考视频，点击生成后才会提交' : '已添加参考图片，点击生成后才会提交')
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '添加引用失败' }
}
defineExpose({
  useAsset,
  canSwitchProject: computed(() => !dirty.value && !draftLocked.value && !opening.value && !generation.locked.value && !elementUse.pending.value),
  useElements: elementUse.useElements,
  using: elementUse.pending,
  useError: elementUse.error,
})
const taskId = ref<string>()
const progress = useCreationProgress(props.activity, () => generation.acceptedId.value, folders => emit('assetsChanged', folders), id => { taskId.value = id })
// 发送前阻止重复点击；请求发出后允许新的独立生成。
const trackedTaskId = ref<string>()
watch(() => props.projectId, () => { trackedTaskId.value = undefined })
watch(() => progress.running.value?.id, id => { if (id) trackedTaskId.value = id }, { immediate: true })
const latestSubmitted = computed(() => {
  const id = generation.acceptedId.value || trackedTaskId.value
  // 新任务刚受理、快照尚未返回时，不把上一个任务的结果当成本次结果。
  return progress.rows.value.find(row => row.id === id) || (generation.acceptedId.value ? undefined : progress.running.value)
})
const submissionFeedback = computed(() => latestSubmitted.value ? generationSubmissionFeedback(latestSubmitted.value) : undefined)
const generationBusy = computed(() => Boolean(submissionFeedback.value?.busy))
const buttonLabel = computed(() => generation.submitting.value ? '保存任务…' : generation.checking.value || generation.generating.value ? '检查参数…' : submissionFeedback.value?.label)
async function checkGeneration() {
  if (draftLocked.value || generationBusy.value) return
  if (elementTarget.requested.value && (!elementTarget.target.value || kind.value !== 'image'))
    return
  if (!(await formRef.value?.validate().catch(() => false)) || draftLocked.value) return
  await generation.generate()
}
const rules = { prompt: [{ max: 50000, message: '提示词不能超过50000字符', trigger: 'blur' }] }
</script>

<template>
  <section class="creation-panel" :class="{ 'creation-dock': dock }">
    <GenerationFeedbackCard v-if="latestSubmitted || progress.awaitingAccepted.value"
      :row="latestSubmitted" :awaiting="progress.awaitingAccepted.value" :error="progress.error.value" :loading="progress.loading.value"
      @refresh="progress.reload()" @detail="taskId = $event" />
    <ElForm ref="formRef" :model="form" :rules="rules" class="composer-validation" @submit.prevent>
    <ElFormItem prop="prompt">
    <CreationComposer v-model:prompt="prompt" :kind="kind" :models="models" :selected="selected"
      :job-busy="generationBusy" :job-label="buttonLabel" :job-spinning="submissionFeedback?.spinning" :active-task="generation.sameAsAccepted.value && !generationBusy" :parameters="parameters" :reference-count="references.length" :disabled="editingLocked || opening || generation.locked.value || generation.generating.value"
      :loading="loading" :saving="saving" :checking="generation.generating.value || generation.submitting.value"
      :estimate="generation.visibleEstimate.value ? `${generation.visibleEstimate.value.amount} ${generation.visibleEstimate.value.currency}` : undefined"
      @kind="changeKind" @model="choose" @parameter="setParameter" @reference="(source, anchor) => referencePicker?.show(source, anchor)"
      @generate="checkGeneration">
      <template #prompt>
        <ComposerPrompt ref="promptEditor" v-model="promptDocument" :references="references" :project-id="projectId" :model="selected"
          :context="kind" :disabled="editingLocked || opening || generation.locked.value || generation.generating.value"
          @apply="value => { promptDocument = value.prompt; references = value.references }" />
      </template>
      <template #history>
        <button type="button" class="creation-history-toggle" title="已保存的创作参数" aria-label="已保存的创作参数" :aria-expanded="draftsOpen" aria-controls="creation-parameter-history" @click="draftsOpen = !draftsOpen"><IconHistory :size="16" /></button>
      </template>
      <template v-if="imageReferences.length" #images>
        <SelectedReference :project-id="projectId" v-for="item in imageReferences" :key="`${item.referenceKey}:${item.assetVersionId}:${item.mediaRole}`" :item="item" :disabled="draftLocked || opening || generation.locked.value" :protected="protectedReferenceKeys.includes(item.referenceKey)" @remove="removeSelected(item)" />
      </template>
      <template v-if="videoReference" #video="{ label }">
        <SelectedReference :project-id="projectId" :item="videoReference" video :label="label" :disabled="draftLocked || opening || generation.locked.value" :protected="protectedReferenceKeys.includes(videoReference.referenceKey)" @remove="removeSelected(videoReference)" @edit="anchor => referencePicker?.show('asset', anchor)" />
      </template>
    </CreationComposer>
    </ElFormItem>
    </ElForm>
    <div class="composer-notices">
    <p v-if="autoSaveError" class="compact-notice" role="alert">
      自动保存失败，内容仍保留
      <button type="button" :disabled="saving" @click="save(true)">{{ saving ? '正在重试…' : '重试保存' }}</button>
    </p>
    <p v-if="!loading && !models.length" class="compact-notice">暂无已授权模型，请由管理员配置；仍可编写描述、添加参考素材并保存创作参数。</p>

    <p v-if="missingModel" class="compact-notice" role="alert">原模型暂不可用，提示词与参数已保留，请重新选择模型。</p>
    <p v-if="draftUncertain" class="compact-notice" role="alert">创作参数保存结果待确认，请点击重试保存。</p>
    <p v-if="error" class="compact-notice" role="alert">{{ error }}</p>
    </div>
    <div v-show="draftsOpen" id="creation-parameter-history" class="creation-expanded">

    <section
      v-if="elementTarget.requested.value"
      class="creation-element-target"
      aria-label="元素图片生成目标"
    >
      <p v-if="elementTarget.loading.value" role="status">正在核验目标元素…</p>
      <p v-if="elementTarget.error.value" class="project-error" role="alert">
        {{ elementTarget.error.value }}
      </p>
      <p v-if="elementTarget.target.value">
        目标元素：{{ elementTarget.target.value.name }} · @{{ elementTarget.target.value.alias }}
      </p>
      <p class="muted">
        确认图片模式与提示词后点击生成。此入口不会自动生成或覆盖元素；满意作品归档后再加入元素。
      </p>
      <Button
        v-if="kind !== 'image'"
        variant="outline"
        :disabled="draftLocked || opening || generation.locked.value"
        @click="changeKind('image')"
        >切换为图片创作</Button
      >
      <Button
        variant="ghost"
        :disabled="generation.locked.value || elementTarget.loading.value"
        @click="elementTarget.reload"
        >重新核验目标</Button
      >
      <RouterLink :to="elementTarget.returnTo.value">返回元素列表</RouterLink>
    </section>
    <div class="workspace-section-heading creation-drafts-heading">
      <div>
        <h2>已保存的{{ kind === 'image' ? '图片' : '视频' }}创作参数</h2>
        <p class="muted">保存提示词、模型、参数和参考素材；选择一条可载入创作栏继续编辑。</p>
      </div>
      <Button variant="ghost" class="creation-drafts-close" aria-label="关闭创作参数记录" title="关闭" @click="draftsOpen = false"><IconX :size="16" /></Button>
    </div>
    <section class="creation-drafts" aria-label="已保存的创作参数列表">
      <p v-if="draftsLoading" role="status">读取中…</p>
      <p v-else-if="!drafts.length" class="muted">当前项目暂无已保存的{{ kind === 'image' ? '图片' : '视频' }}创作参数。</p>
      <ul>
        <li v-for="item in drafts" :key="item.id">
          <button
            type="button"
            :disabled="draftLocked || opening || generation.locked.value"
            @click="openDraft(item.id)"
          >
            <strong>{{ item.kind === 'image' ? '图像' : '视频' }}</strong
            ><span>{{ item.promptExcerpt || '空白提示词' }}</span
            ><time>{{ new Date(item.updateTime).toLocaleString() }}</time>
          </button>
        </li>
      </ul>
      <StudioPagination
        v-if="draftTotal > 0"
        v-model:current-page="draftPage"
        :page-size="10"
        :total="draftTotal"
        size="small"
        layout="total,prev,pager,next"
        @current-change="loadDrafts"
      />
    </section>
    <p v-if="opening" role="status">正在载入创作参数…</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    </div>
    <DraftReferences ref="referencePicker" picker-only link-prompt @element-select="(candidate, role) => promptEditor?.insert(candidate, role)" @uploaded="emit('assetsChanged', [body.folderId ?? null])" @picker-open="pickerOpen = $event"
      :folder-id="body.folderId ?? null" v-model="references" :project-id="projectId"
      :disabled="draftLocked || opening || generation.locked.value" :protected-keys="protectedReferenceKeys" :model="selected" />


    <section v-if="(generation.quote.value && !generation.quote.value.valid) || generation.error.value || generation.uncertain.value" class="generation-submit">
      <p v-if="generation.error.value" class="project-error" role="alert">
        {{ generation.error.value }}
      </p>
      <ul v-if="generation.quote.value && !generation.quote.value.valid">
        <li v-for="(issue, index) in generation.quote.value.issues" :key="index">
          {{ issue.message }}
        </li>
      </ul>
      <template v-if="generation.uncertain.value">
        <p role="alert">上次提交结果尚未确认，请确认原请求结果，不要新建生成。待确认请求仅保留在当前登录会话内；请勿刷新页面或退出登录，强制离开后先到任务列表核查。</p>
        <Button :disabled="generation.submitting.value" @click="generation.submit">{{
          generation.submitting.value ? '正在确认…' : '确认原请求结果'
        }}</Button>
      </template>
      <p v-if="generation.acceptedId.value" role="status">
        任务已受理：{{ generation.acceptedId.value }}，后续结果请查看任务详情。
      </p>
      <Button
        v-if="generation.acceptedId.value"
        variant="ghost"
        @click="taskId = generation.acceptedId.value"
        >查看任务详情</Button
      >
    </section>

    <GenerationDetail v-model="taskId" />
  </section>
</template>

<style scoped>
.creation-history-toggle { display:flex; align-items:center; justify-content:center; padding:6px; border:0; border-radius:6px; background:transparent; color:var(--muted-foreground); cursor:pointer; }
.creation-history-toggle:hover,.creation-history-toggle[aria-expanded="true"] { background:var(--border); color:var(--foreground); }
.creation-history-toggle:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }


.compact-notice button { border:0; background:transparent; color:var(--muted-foreground); cursor:pointer; margin-left:10px; text-decoration:underline; }
.compact-notice { margin:6px 12px; font-size:12px; color:var(--muted-foreground); }
/* 不使用 transform 居中，避免后代固定弹层被限制在创作栏内。 */
.creation-dock { position:fixed; z-index:20; bottom:50px; left:260px; right:0; width:min(920px, calc(100vw - 330px)); margin:0 auto !important; overflow:visible; }
/* 提示不参与底部定位计算，避免模型加载或类型切换时整栏上下跳动。 */
.creation-dock .composer-notices { position:absolute; top:100%; left:0; right:0; overflow:visible; }
.creation-expanded { max-height:55vh; overflow:auto; padding:12px; margin-bottom:8px; font-size:12px; border:1px solid var(--border); border-radius:16px; background:var(--background); }
.creation-dock .creation-expanded { position:absolute; bottom:100%; left:0; right:0; box-shadow:0 -12px 40px #0002; }
.creation-dock .generation-submit { position:absolute; bottom:100%; left:0; right:0; max-height:50vh; overflow:auto; }
@media(max-width:800px) { .creation-dock { left:0; width:calc(100vw - 28px); bottom:50px; } }

.creation-element-target {
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-raised);
}
.creation-element-target a {
  color: var(--foreground);
  margin-left: 12px;
}
.generation-submit {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}
.creation-panel {
  max-width: 1000px;
  margin: 24px auto;
}
.creation-drafts {
  margin-bottom: 8px;
  padding: 0;
  border: 0;
  border-radius: 8px;
}
.creation-drafts summary {
  cursor: pointer;
  margin-bottom: 12px;
}
.creation-drafts ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.creation-drafts li button {
  display: flex;
  gap: 8px;
  width: 100%;
  padding: 8px;
  font-size: 12px;
  line-height: 1.4;
  text-align: left;
  color: var(--foreground);
  background: var(--surface);
  border: 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
}
.creation-drafts li button:hover {
  background: var(--surface-hover);
}
.creation-drafts li button:focus-visible {
  outline: 2px solid var(--focus);
}
.creation-drafts li button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.creation-drafts li span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.creation-drafts time {
  color: var(--muted-foreground);
  font-size: 12px;
}
/* 只保留校验容器，不呈现第二套表单。 */
.composer-validation :deep(.el-form-item) { margin:0; }
.composer-validation :deep(.el-form-item__content) { display:block; line-height:normal; }
</style>

<style scoped>

.creation-drafts-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin:0 0 10px; position:sticky; top:-12px; padding:8px 0; background:var(--background); z-index:1; }
.creation-drafts-heading h2 { font-size:14px; line-height:1.4; margin:0 0 4px; }
.creation-drafts-heading p { font-size:12px; line-height:1.5; margin:0; }
.creation-drafts-close { flex:0 0 28px; width:28px; height:28px; min-height:28px; padding:5px; border-radius:6px; }
.creation-drafts > p { margin:6px 0; font-size:12px; }
.creation-drafts :deep(.el-pagination) { margin-top:8px; --el-pagination-font-size:12px; --el-pagination-button-width:24px; --el-pagination-button-height:24px; }
.creation-drafts :deep(.el-pagination__total),
.creation-drafts :deep(.el-pager li) { font-size:12px; }
</style>
