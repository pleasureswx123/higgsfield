<script setup lang="ts">
import type { Asset } from '@/api/assets'
import type { PropertyDefinition, ElementRecord } from '@/api/elements'
import { ref, toRef, defineAsyncComponent, watch } from 'vue'
import type { DraftReference } from '@/api/creation'
import {
  ElDialog,
  ElMessage,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  type FormRules,
} from 'element-plus'
import {
  IconPhoto,
  IconStar,
  IconStarFilled,
  IconPlus,
  IconMaximize,
  IconTrash,
  IconInfoCircle,
  IconCategory,
  IconUserCheck,
  IconCircleDashed,
} from '@tabler/icons-vue'
import Button from '@/components/ui/Button.vue'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { useElementPreviewDownload } from '@/composables/useElementPreviewDownload'
import { useElementEditor } from '@/composables/useElementEditor'
import ReferenceThumbnail from './ReferenceThumbnail.vue'
import ElementImageLightbox from './ElementImageLightbox.vue'
import ElementPropertyPopover from './ElementPropertyPopover.vue'
const props = defineProps<{
  initialAsset?: Asset
  projectId: string
  visible?: boolean
  elementId: string | null
  actions: string[]
  using?: boolean
  useError?: string
}>()
const emit = defineEmits<{ close: []; saved: []; use: [element: ElementRecord] }>()
const previewExpanded = ref(false)
const ElementMediaPicker = defineAsyncComponent(() => import('./DraftReferences.vue'))
const referencePicker = ref<{ show: (kind: 'asset', anchor: HTMLElement) => void }>()
const referencePickerOpen = ref(false)
const pickerContainer = ref<HTMLElement>()
const pickerReferences = ref<DraftReference[]>([])
function showReferencePicker(event: MouseEvent) {
  if (!canEdit.value || locked.value || previewLoading.value || previewError.value || props.using) return
  const target = event.currentTarget as HTMLElement
  pickerContainer.value = target.closest<HTMLElement>('.el-dialog') || undefined
  const anchor = pickerContainer.value?.querySelector<HTMLElement>('.element-add-media') || target
  referencePicker.value?.show('asset', anchor)
}
const propertyPopover = ref<InstanceType<typeof ElementPropertyPopover>>()
const propertyEditBusy = ref<Record<string, boolean>>({})
function propertyRenamed(definition: PropertyDefinition) {
  const item = properties.value.find(item => item.definition.propertyKey === definition.propertyKey)
  if (item) {
    delete newerDefinitions.value[item.definition.id]
    item.definition = definition
  }
}
function propertyChanged(definition: PropertyDefinition) {
  const existing = properties.value.find(
    (item) => item.definition.propertyKey === definition.propertyKey,
  )
  if (existing) newerDefinitions.value[existing.definition.id] = definition
  else properties.value.push({ definition, value: null })
}
const {
  active,
  form,
  fields,
  properties,
  newerDefinitions,
  adoptDefinition,
  removeProperty,
  members,
  loading,
  saving,
  uncertain,
  conflict,
  aliasManual,
  aliasError,
  markAliasManual,
  resetAliasSuggestion,
  locked,
  retry,
  error,
  canEdit,
  canReview,
  allowed,
  selectedVersion,
  previewUrl,
  previewKind,
  previewLoading,
  previewError,
  addReferenceMedia,
  primary,
  removeMedia,
  save,
  confirmClose,
} = useElementEditor(
  props.projectId,
  props.elementId,
  toRef(props, 'actions'),
  () => emit('saved'),
  () => props.visible !== false,
  props.initialAsset,
)
const previewDownload = useElementPreviewDownload(() => active.value && previewExpanded.value && props.actions.includes('asset:download'))
watch(previewDownload.message, value => { if (value) ElMessage.error(value) })
watch([active, selectedVersion], () => { previewExpanded.value = false })
const categories = [
  { value: 'character', label: '角色' },
  { value: 'scene', label: '场景' },
  { value: 'prop', label: '道具' },
  { value: 'other', label: '其他' },
]
const statuses = [
  { value: 'none', label: '无状态' },
  { value: 'working', label: '制作中' },
  { value: 'review', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
]
const rules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请输入名称', trigger: 'blur' }],
  alias: [{ required: true, whitespace: true, message: '请输入项目内唯一别名', trigger: 'blur' }],
}
async function close() {
  if (previewExpanded.value) return
  if (
    propertyPopover.value?.locked ||
    propertyPopover.value?.open ||
    referencePickerOpen.value ||
    Object.values(propertyEditBusy.value).some(Boolean) ||
    props.using
  )
    return
  if (await confirmClose()) emit('close')
}
async function selectImage(version: string) {
  if (version === selectedVersion.value) return
  selectedVersion.value = version
}
async function removeSelectedImage() {
  if (fields.media.length <= 1) return
  removeMedia(selectedVersion.value)
}
</script>
<template>
  <ElDialog
    :model-value="active"
    :title="elementId ? '编辑元素' : '新建元素'"
    width="min(1280px, calc(100vw - 48px))"
    top="8dvh"
    class="element-dialog"
    :before-close="close"
    :close-on-click-modal="false"
    :show-close="
      !locked && !using
    "
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading
        :title-id="titleId"
        :title-class="titleClass"
        :title="elementId ? '编辑元素' : '新建元素'"
      />
    </template>
    <p v-if="useError" class="project-error" role="alert">{{ useError }}</p>
    <p v-if="uncertain && !saving" role="alert">
      操作结果尚未确认，请重试确认原请求；确认前不能编辑或关闭。
    </p>
    <p v-if="conflict" role="alert">
      元素版本已变化，当前输入已保留。请先复制需要保留的内容，再关闭并重新打开元素，查看最新版本后编辑。
    </p>
    <p v-if="loading" role="status">正在读取元素资料…</p>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <div v-if="!loading" class="element-editor-layout">
      <section class="element-image-panel">
        <div class="element-image-stage">
          <video
            v-if="previewUrl && previewKind === 'video'"
            :src="previewUrl"
            controls
            playsinline
            preload="metadata"
          />
          <img v-else-if="previewUrl" :src="previewUrl" :alt="fields.name || '元素素材'" />
          <p v-else-if="previewLoading" role="status">正在授权读取素材…</p>
          <p v-else-if="previewError" class="project-error" role="alert">{{ previewError }}</p>
          <div v-else class="element-image-empty">
            <IconPhoto :size="56" />
            <p>添加项目图片或视频，或先保存无素材元素</p>
          </div>
        </div>
        <div class="element-preview-toolbar">
          <div class="element-media-strip">
            <div
              v-for="(media, index) in fields.media"
              :key="media.assetVersionId"
              class="element-media-item"
            >
            <button
              type="button"
              :class="{ active: selectedVersion === media.assetVersionId }"
              :aria-label="`素材 ${index + 1}${media.isPrimary ? '，主图' : ''}`"
              :title="`素材 ${index + 1}${media.isPrimary ? ' · 主图' : ''}`"
              :aria-pressed="selectedVersion === media.assetVersionId"
              @click="selectImage(media.assetVersionId)"
            >
              <ReferenceThumbnail :version-id="media.assetVersionId" fill passive allow-original />
            </button>
            <span
              v-if="fields.media.length > 1 && media.isPrimary"
              class="element-media-primary is-primary"
              title="当前主图"
              aria-hidden="true"
            >
              <IconStarFilled :size="12" />
            </span>
            </div>
            <button
              v-if="canEdit && allowed.includes('asset:read')"
              type="button"
              class="element-add-media"
              title="为当前元素添加素材"
              aria-label="添加素材"
              :disabled="using || locked"
              @click="showReferencePicker"
            >
              <IconPlus :size="20" />
            </button>
          </div>
          <div class="element-media-actions">
            <button
              v-if="canEdit && fields.media.some(media => media.assetVersionId === selectedVersion && !media.isPrimary)"
              type="button"
              title="设为主图"
              aria-label="设为主图"
              :disabled="locked || !!using"
              @click="primary(selectedVersion)"
            >
              <IconStar :size="22" />
            </button>
            <button
              type="button"
              title="放大预览"
              aria-label="放大预览" :disabled="!previewUrl || previewLoading"
              @click="previewExpanded = true"
            >
              <IconMaximize :size="22" />
            </button>
            <button
              v-if="selectedVersion && canEdit && fields.media.length > 1"
              type="button"
              title="移除引用，不删除原素材"
              aria-label="移除素材引用"
              :disabled="using || locked"
              @click="removeSelectedImage"
            >
              <IconTrash :size="22" />
            </button>
          </div>
        </div>
      </section>
      <section class="element-detail-panel">
        <ElForm
          ref="form"
          :model="fields"
          :rules="rules"
          label-position="top"
          class="element-fields"
          @submit.prevent
          :disabled="using || locked || !canEdit"
        >
          <ElFormItem label="分类"
            ><ElSelect v-model="fields.category"
              ><template #prefix><IconCategory :size="18" /></template
              ><ElOption v-for="item in categories" :key="item.value" v-bind="item" /></ElSelect
          ></ElFormItem>
          <ElFormItem v-if="fields.category === 'character'" label="人物性质">
            <div class="flex items-center gap-2">
              <Switch
                v-model="fields.isFictionalPerson"
                class="element-fictional-switch"
                aria-label="虚构人物"
                :disabled="using || locked || !canEdit"
              />
              <span>{{ fields.isFictionalPerson ? '虚构人物' : '不是虚构人物' }}</span>
              <TooltipProvider
                ><Tooltip
                  ><TooltipTrigger as-child
                    ><button type="button" class="element-field-help" aria-label="人物性质说明">
                      <IconInfoCircle :size="15" /></button></TooltipTrigger
                  ><TooltipContent class="element-field-tooltip"
                    >人物角色默认开启；动物等非人物角色请关闭。开启后，支持的模型会自动注册人物素材。</TooltipContent
                  ></Tooltip
                ></TooltipProvider
              >
            </div>
          </ElFormItem>
          <ElFormItem label="名称" prop="name"
            ><ElInput v-model="fields.name" maxlength="200" placeholder="元素名称" /><small
              class="muted"
              >用于展示的名称，例如：角色、场景或道具名称</small
            ></ElFormItem
          >
          <ElFormItem label="元素 ID" prop="alias" :error="aliasError"
            ><template #label
              ><span class="element-field-label"
                >元素 ID
                <TooltipProvider
                  ><Tooltip
                    ><TooltipTrigger as-child
                      ><button type="button" class="element-field-help" aria-label="元素 ID 说明">
                        <IconInfoCircle :size="15" /></button></TooltipTrigger
                    ><TooltipContent class="element-field-tooltip">{{
                      elementId
                        ? '修改名称不会自动改写已有别名。'
                        : '根据名称和分类建议别名；手动修改后保留你的输入。唯一性以保存结果为准。'
                    }}</TooltipContent></Tooltip
                  ></TooltipProvider
                ></span
              ></template
            ><ElInput v-model="fields.alias" maxlength="100" @input="markAliasManual"
              ><template #prepend>@</template></ElInput
            >
            <Button
              v-if="!elementId && aliasManual"
              type="button"
              variant="ghost"
              :disabled="locked || !canEdit"
              @click="resetAliasSuggestion"
              >重置建议</Button
            >
          </ElFormItem>
          <ElFormItem label="描述"
            ><ElInput
              v-model="fields.description"
              type="textarea"
              :rows="4"
              placeholder="描述此元素（可选）"
          /></ElFormItem>
          <ElFormItem label="负责人"
            ><ElSelect
              v-model="fields.performerId"
              clearable
              :value-on-clear="null"
              :disabled="!allowed.includes('member:read')"
              placeholder="未分配"
              ><template #prefix><IconUserCheck :size="18" /></template
              ><ElOption
                v-if="
                  fields.performerId &&
                  !members.some((member) => member.userId === fields.performerId)
                "
                :value="fields.performerId"
                label="原负责人（当前不可选）"
                disabled /><ElOption
                v-for="member in members"
                :key="member.userId"
                :value="member.userId"
                :label="member.displayName" /></ElSelect
          ></ElFormItem>
          <ElFormItem label="状态"
            ><ElSelect v-model="fields.workStatus" :disabled="!canReview"
              ><template #prefix><IconCircleDashed :size="18" /></template
              ><ElOption v-for="item in statuses" :key="item.value" v-bind="item" /></ElSelect
          ></ElFormItem>
          <h4 class="element-properties-heading">自定义属性</h4>
          <ElFormItem
            v-for="property in properties"
            :key="property.definition.propertyKey"
            :label="property.definition.name"
            class="element-custom-property"
          >
            <template #label>
              <span class="element-property-name">{{ property.definition.name }}</span>
              <span v-if="canEdit" class="element-property-actions">
                <ElementPropertyPopover v-if="allowed.includes('element:configure')" :project-id="projectId" :visible="active" :definition="property.definition" :attached-definitions="properties.map(item => item.definition)" :disabled="locked || !!using" @changed="propertyRenamed" @busy="propertyEditBusy[property.definition.propertyKey] = $event" />
                <Button type="button" variant="ghost" class="element-property-icon" :aria-label="`移除当前元素属性 ${property.definition.name}`" :disabled="locked || using || propertyEditBusy[property.definition.propertyKey]" @click="removeProperty(property.definition.id)"><IconTrash :size="16" /></Button>
              </span>
            </template>
            <ElInput
              v-if="property.definition.valueType === 'text'"
              placeholder="未填写"
              :model-value="typeof property.value === 'string' ? property.value : ''"
              @update:model-value="property.value = $event"
            />
            <ElSelect
              v-else
              v-model="property.value"
              :multiple="property.definition.valueType === 'multi_select'"
              clearable
              placeholder="未填写"
              ><ElOption
                v-for="option in property.definition.options"
                :key="option"
                :value="option"
                :label="option"
            /></ElSelect>
            <button
              v-if="canEdit && newerDefinitions[property.definition.id]"
              type="button"
              class="folder-text-button"
              :disabled="using || locked"
              @click="adoptDefinition(property.definition.id)"
            >
              采用最新定义 v{{ newerDefinitions[property.definition.id]?.versionNo }}
            </button>
          </ElFormItem>
          <ElementPropertyPopover
            ref="propertyPopover"
            v-if="canEdit && allowed.includes('element:configure')"
            :project-id="projectId"
            :attached-definitions="properties.map(item => item.definition)"
            :visible="active"
            :disabled="locked || !!using"
            @changed="propertyChanged"
          />
          <p v-else-if="!properties.length" class="muted">暂无自定义属性</p>
        </ElForm>
      </section>
    </div>
    <template #footer><Button
        variant="ghost"
        :disabled="using || locked"
        @click="close"
        >取消</Button
      ><Button
        v-if="canEdit && !uncertain"
        :disabled="using || saving || loading || conflict"
        @click="save"
        >{{ saving ? '保存中…' : elementId ? '保存' : '创建' }}</Button
      ><Button v-if="uncertain" :disabled="saving || loading || using" @click="retry">{{
        saving ? '正在确认…' : '重试确认原请求'
      }}</Button></template
    >
    <ElementImageLightbox v-if="previewExpanded && previewUrl && previewKind === 'image'"
      :url="previewUrl" :download-disabled="!actions.includes('asset:download') || previewDownload.pending.value || previewDownload.resolving.value"
      @close="previewExpanded = false" @download="previewDownload.download(selectedVersion)" />
    <ElDialog v-if="previewKind === 'video'" v-model="previewExpanded" title="视频放大预览" fullscreen append-to-body class="element-video-lightbox" :show-close="true">
      <video v-if="previewExpanded" :src="previewUrl" controls />
    </ElDialog>
    <ElementMediaPicker
      ref="referencePicker"
      v-model="pickerReferences"
      picker-only
      element-media
      :required-media-type="fields.media.length ? previewKind : undefined"
      :project-id="projectId"
      :disabled="!active || !canEdit || locked || !!using"
      :protected-keys="[]"
      :selected-version-ids="fields.media.map(item => item.assetVersionId)"
      :append-to="pickerContainer"
      @picker-open="referencePickerOpen = $event"
      @media-select="addReferenceMedia"
      @media-deselect="versions => versions.forEach(removeMedia)"
    />
  </ElDialog>
</template>
<style scoped>
.element-detail-panel {
  min-width: 0;
  min-height: 0;
  overflow: auto;
}
.element-detail-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.element-detail-tabs [aria-pressed='true'] {
  background: var(--surface-raised);
  box-shadow: inset 0 -2px var(--focus);
}
.element-comments {
  padding: 8px 20px;
}
</style>
