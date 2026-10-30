<script setup lang="ts">
import { ElForm, ElFormItem, ElInput, ElInputNumber, ElOption, ElPagination, ElSelect, ElSwitch } from 'element-plus'

import type { Asset } from '@/api/assets'
import { selectCandidate } from '@/utils/draftReferences'
import CreationComposer from '@/components/creation/CreationComposer.vue'
import { modelAvailabilityMessage } from '@/utils/modelAvailability'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import { useElementUse } from '@/composables/useElementUse'
import { useElementGenerationTarget } from '@/composables/useElementGenerationTarget'
import { useCreationDraft } from '@/composables/useCreationDraft'
import type { Scalar } from '@/api/creation'
import DraftReferences from './DraftReferences.vue'
import SelectedReference from './SelectedReference.vue'
import type { DraftReference } from '@/api/creation'
import PromptEditor from './PromptEditor.vue'
import GenerationDetail from './GenerationDetail.vue'
import ProjectBudgetStatus from './ProjectBudgetStatus.vue'
import { useGenerationSubmit } from '@/composables/useGenerationSubmit'
const props = defineProps<{ projectId: string; initialPrompt?: string; initialKind?: 'image' | 'video'; dock?: boolean }>()
const emit = defineEmits<{ assetsChanged: [] }>()
const route = useRoute()
const advanced = ref(false)
const referencePicker = ref<InstanceType<typeof DraftReferences>>()
const pickerOpen = ref(false)
const {
  body,
  kind,
  promptDocument,
  prompt,
  richPrompt,
  models,
  selected,
  parameters,
  q,
  page,
  total,
  loading,
  saving,
  autoSaveError,
  uncertain: draftUncertain,
  locked: draftLocked,
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
  newDraft,
  load,
  search,
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
const imageReferences = computed(() => references.value.filter(item => item.mediaRole !== 'reference_video'))
const videoReference = computed(() => references.value.find(item => item.mediaRole === 'reference_video'))
function removeSelected(item: DraftReference) {
  if (draftLocked.value || opening.value || generation.locked.value || protectedReferenceKeys.value.includes(item.referenceKey)) return
  references.value = references.value.filter(value => value !== item).map((value, ordinal) => ({ ...value, ordinal }))
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
async function checkGeneration() {
  if (draftLocked.value) return
  if (elementTarget.requested.value && (!elementTarget.target.value || kind.value !== 'image'))
    return
  if (!(await formRef.value?.validate().catch(() => false)) || draftLocked.value) return
  await generation.generate()
}
const rules = { prompt: [{ max: 50000, message: '提示词不能超过50000字符', trigger: 'blur' }] }
</script>

<template>
  <section class="creation-panel" :class="{ 'creation-dock': dock }">
    <CreationComposer v-model:prompt="prompt" :kind="kind" :models="models" :selected="selected"
      :parameters="parameters" :reference-count="references.length" :disabled="draftLocked || opening || generation.locked.value || generation.generating.value"
      :prompt-readonly="richPrompt" :loading="loading" :saving="saving" :checking="generation.generating.value || generation.submitting.value"
      :estimate="generation.visibleEstimate.value ? `${generation.visibleEstimate.value.amount} ${generation.visibleEstimate.value.currency}` : undefined"
      @kind="changeKind" @model="choose" @parameter="setParameter" @reference="(source, anchor) => referencePicker?.show(source, anchor)"
      @generate="checkGeneration">
      <template v-if="imageReferences.length" #images>
        <SelectedReference v-for="item in imageReferences" :key="`${item.referenceKey}:${item.assetVersionId}:${item.mediaRole}`" :item="item" :disabled="draftLocked || opening || generation.locked.value" :protected="protectedReferenceKeys.includes(item.referenceKey)" @remove="removeSelected(item)" />
      </template>
      <template v-if="videoReference" #video="{ label }">
        <SelectedReference :item="videoReference" video :label="label" :disabled="draftLocked || opening || generation.locked.value" :protected="protectedReferenceKeys.includes(videoReference.referenceKey)" @remove="removeSelected(videoReference)" @edit="anchor => referencePicker?.show('asset', anchor)" />
      </template>
    </CreationComposer>
    <div class="composer-notices">
    <p class="compact-notice" role="status">
      {{ saving ? '正在自动保存…' : autoSaveError ? '自动保存失败，内容仍保留' : dirty ? '等待自动保存…' : draft ? '已自动保存' : '编辑后自动保存草稿' }}
      <button v-if="autoSaveError" type="button" :disabled="saving" @click="save(true)">重试保存</button>
      <button type="button" @click="advanced = !advanced">{{ advanced ? '收起草稿' : '我的草稿' }}</button>
    </p>
    <p v-if="!loading && !models.length" class="compact-notice">暂无已授权模型，请由管理员配置；仍可编写描述、添加参考素材并保存草稿。</p>
    <p v-if="richPrompt" class="compact-notice">当前包含元素引用或富文本，请在“我的草稿”中编辑，保留引用关系。</p>

    <p v-if="error" class="compact-notice" role="alert">{{ error }}</p>
    </div>
    <div v-show="advanced" class="creation-expanded">

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
        确认图片模式与提示词后再预检、提交。此入口不会自动生成或覆盖元素；满意作品归档后再加入元素。
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
    <div class="workspace-section-heading">
      <div>
        <h2>创作详情</h2>
        <p class="muted">先记录提示词与模型参数，再继续完善创作。</p>
        <p class="muted">保存位置：{{ body.folderId ? `目录 #${body.folderId}` : '项目根目录' }}。已有内容保留发起目录；切换目录后可点击“新建草稿”开始。</p>
        <p v-if="body.sourceJobId" class="muted">来源任务 #{{ body.sourceJobId }}。提交会创建新任务并可能产生新的费用，请先检查输入与预估费用。</p>
      </div>
      <span class="muted">{{ dirty ? '未保存' : draft ? '已保存的草稿' : '新草稿' }}</span>
    </div>
    <details class="creation-drafts">
      <summary>我的草稿（{{ draftTotal }}）</summary>
      <div class="creation-kind">
        <Button variant="outline" :disabled="draftsLoading" @click="loadDrafts">刷新列表</Button
        ><Button
          variant="outline"
          :disabled="draftLocked || opening || generation.locked.value"
          @click="newDraft"
          >新建草稿</Button
        >
      </div>
      <p v-if="draftsLoading" role="status">读取中…</p>
      <p v-else-if="!drafts.length" class="muted">当前项目暂无你的草稿。</p>
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
      <el-pagination
        v-if="draftTotal > 10"
        v-model:current-page="draftPage"
        :page-size="10"
        :total="draftTotal"
        layout="prev,pager,next"
        @current-change="loadDrafts"
      />
    </details>
    <div class="creation-kind">
      <Button
        :variant="kind === 'image' ? 'default' : 'ghost'"
        :disabled="draftLocked || opening || generation.locked.value"
        @click="changeKind('image')"
        >图像</Button
      ><Button
        :variant="kind === 'video' ? 'default' : 'ghost'"
        :disabled="draftLocked || opening || generation.locked.value"
        @click="changeKind('video')"
        >视频</Button
      >
    </div>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="draftUncertain" role="alert">
      草稿保存结果尚未确认，请重试原保存请求，确认结果后再继续编辑。
    </p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="opening" role="status">正在打开草稿…</p>
    <p v-if="missingModel" class="project-error">
      原模型配置暂不可用，已保留模型版本和参数。可稍后重新打开，或明确选择其他模型。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="draftLocked || opening || generation.locked.value"
      label-position="top"
      class="creation-composer"
      @submit.prevent
    >
      <el-form-item label="描述你的创意" prop="prompt"
        ><PromptEditor
          v-model="promptDocument"
          :disabled="draftLocked || opening || generation.locked.value"
          :references="references"
      /></el-form-item>
      <div class="creation-model-search">
        <el-input
          v-model="q"
          placeholder="搜索模型名称"
          clearable
          :disabled="draftLocked || opening || generation.locked.value"
          @keyup.enter="search"
          @clear="search"
        /><Button
          variant="outline"
          :disabled="loading || draftLocked || opening || generation.locked.value"
          @click="search"
          >查找</Button
        >
      </div>
      <el-form-item label="项目已授权模型">
        <el-select
          :model-value="selected?.versionId || ''"
          :loading="loading"
          clearable
          placeholder="选择模型；也可以仅保存提示词"
          @update:model-value="choose"
        >
          <el-option
            v-if="selected && !models.some((item) => item.versionId === selected?.versionId)"
            :label="selected.displayName"
            :value="selected.versionId"
          />
          <el-option
            v-for="model in models"
            :key="model.versionId"
            :value="model.versionId"
            :label="`${model.displayName} ${model.menuMeta.releaseLabel}`"
          />
        </el-select>
      </el-form-item>
      <el-pagination
        v-if="total > 20"
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev,pager,next"
        :disabled="draftLocked || opening || generation.locked.value"
        @current-change="load"
      />
      <p v-if="!loading && !models.length" class="muted">
        暂无匹配的已授权发布模型。可先保存提示词，或联系管理员配置项目模型。
      </p>
      <div v-if="selected" class="creation-parameters">
        <p class="muted" role="status">
          {{ modelAvailabilityMessage(selected.availability?.reasonCode) }}
        </p>
        <el-form-item
          v-for="(rule, name) in selected.parametersSchema.properties"
          :key="name"
          :label="`${name}${selected.parametersSchema.required.includes(name) ? '（生成前必填）' : ''}`"
        >
          <el-select
            v-if="rule.enum"
            :model-value="parameters[name]"
            clearable
            placeholder="使用默认值或选择"
            @update:model-value="(value: Scalar) => setParameter(name, value)"
            ><el-option
              v-for="(value, index) in rule.enum"
              :key="index"
              :label="String(value)"
              :value="value"
          /></el-select>
          <el-switch
            v-else-if="rule.type === 'boolean'"
            :model-value="parameters[name] === true"
            @update:model-value="(value: Scalar) => setParameter(name, value)"
          />
          <el-input-number
            v-else-if="rule.type === 'number' || rule.type === 'integer'"
            :model-value="
              typeof parameters[name] === 'number' ? (parameters[name] as number) : undefined
            "
            :min="rule.minimum ?? undefined"
            :max="rule.maximum ?? undefined"
            :precision="rule.type === 'integer' ? 0 : undefined"
            @update:model-value="(value: number | undefined) => setParameter(name, value)"
          />
          <el-input
            v-else
            :model-value="String(parameters[name] ?? '')"
            :maxlength="rule.maxLength ?? undefined"
            @update:model-value="(value: string) => setParameter(name, value)"
          />
        </el-form-item>
      </div>
      <DraftReferences ref="referencePicker" @uploaded="emit('assetsChanged')" @picker-open="pickerOpen = $event"
        :folder-id="body.folderId ?? null"
        v-model="references"
        :project-id="projectId"
        :disabled="draftLocked || opening || generation.locked.value"
        :protected-keys="protectedReferenceKeys"
        :model="selected"
      />
      <ProjectBudgetStatus :project-id="projectId" :refresh-key="generation.acceptedId.value" />
      <div class="creation-actions">
        <p class="muted">保存草稿不产生生成费用。</p>
        <Button :disabled="saving || opening || generation.locked.value" @click="save">{{
          saving ? '保存中…' : draftUncertain ? '重试原保存请求' : '保存草稿'
        }}</Button>
      </div>
    </el-form>
    </div>
    <section v-if="(generation.quote.value && !generation.quote.value.valid) || generation.error.value || generation.uncertain.value || generation.acceptedId.value" class="generation-submit">
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
.compact-notice button { border:0; background:transparent; color:var(--muted-foreground); cursor:pointer; margin-left:10px; text-decoration:underline; }
.compact-notice { margin:6px 12px; font-size:12px; color:var(--muted-foreground); }
.creation-dock { position:fixed; z-index:20; bottom:50px; left:calc(260px + (100vw - 260px) / 2); transform:translateX(-50%); width:min(920px, calc(100vw - 330px)); margin:0 !important; }
/* 提示不参与底部定位计算，避免模型加载或类型切换时整栏上下跳动。 */
.creation-dock .composer-notices { position:absolute; top:100%; left:0; right:0; max-height:44px; overflow:auto; }
.creation-expanded { max-height:55vh; overflow:auto; padding:20px; margin-bottom:8px; border:1px solid var(--border); border-radius:16px; background:var(--background); }
.creation-dock .creation-expanded { position:absolute; bottom:100%; left:0; right:0; box-shadow:0 -12px 40px #0002; }
.creation-dock .generation-submit { position:absolute; bottom:100%; left:0; right:0; max-height:50vh; overflow:auto; }
@media(max-width:800px) { .creation-dock { left:50%; width:calc(100vw - 28px); bottom:50px; } }

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
  margin-bottom: 20px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
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
  gap: 12px;
  width: 100%;
  padding: 12px;
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
.creation-kind {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.creation-composer {
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--surface-raised);
}
.creation-model-search {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.creation-parameters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0 16px;
  margin-top: 16px;
}
.creation-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.creation-actions p {
  max-width: 70%;
}
:deep(.el-textarea__inner) {
  background: var(--surface);
  border-radius: 12px;
}
@media (max-width: 600px) {
  .creation-actions {
    align-items: flex-start;
    flex-direction: column;
  }
  .creation-actions p {
    max-width: 100%;
  }
}
</style>
