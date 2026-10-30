<script setup lang="ts">
import type { Asset } from '@/api/assets'
import type { PropertyDefinition, ElementRecord } from '@/api/elements'
import { ref, toRef } from 'vue'
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  ElPagination,
  type FormRules,
} from 'element-plus'
import { IconPhoto, IconPlus, IconRefresh, IconMaximize, IconMinimize, IconTrash } from '@tabler/icons-vue'
import Button from '@/components/ui/Button.vue'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { useElementDownload } from '@/composables/useElementDownload'
import { useElementEditor } from '@/composables/useElementEditor'
import DirectoryMoveDialog from './DirectoryMoveDialog.vue'
import ElementCopyDialog from './ElementCopyDialog.vue'
import ElementHistoryDialog from './ElementHistoryDialog.vue'
import MediaComments from './MediaComments.vue'
import ReferenceThumbnail from './ReferenceThumbnail.vue'
import PropertyDefinitionsDialog from './PropertyDefinitionsDialog.vue'
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
const mover = ref<InstanceType<typeof DirectoryMoveDialog>>()
const copier = ref<InstanceType<typeof ElementCopyDialog>>()
const copyOpen = ref(false),
  historyOpen = ref(false)
const previewExpanded = ref(false)
const propertiesOpen = ref(false)
function propertyChanged(definition: PropertyDefinition) {
  const existing = properties.value.find(item => item.definition.propertyKey === definition.propertyKey)
  if (existing) newerDefinitions.value[existing.definition.id] = definition
  else properties.value.push({ definition, value: null })
}
const detailTab = ref<'info' | 'comments'>('info')
const comments = ref<InstanceType<typeof MediaComments>>()
const {
  active,
  form,
  fields,
  properties,
  newerDefinitions,
  adoptDefinition,
  members,
  detail,
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
  dirty,
  canEdit,
  canReview,
  canRemove,
  allowed,
  selectedVersion,
  previewUrl,
  previewKind,
  pickerKind,
  previewLoading,
  previewError,
  pickerOpen,
  candidates,
  pickerPage,
  pickerTotal,
  pickerSearch,
  pickerLoading,
  pickerError,
  showPicker,
  searchCandidates,
  addMedia,
  primary,
  removeMedia,
  moveMedia,
  save,
  remove,
  confirmClose,
} = useElementEditor(props.projectId, props.elementId, toRef(props, 'actions'), () => emit('saved'), () => props.visible !== false, props.initialAsset)
const downloader = useElementDownload(
  () =>
    active.value &&
    props.actions.includes('asset:download') &&
    !!detail.value &&
    !locked.value &&
    !props.using &&
    !mover.value?.locked &&
    !copier.value?.locked,
)
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
  if (propertiesOpen.value || downloader.pending.value || props.using || mover.value?.locked || copier.value?.locked) return
  if (comments.value && !(await comments.value.confirmLeave())) return
  if (await confirmClose()) emit('close')
}
async function useElement() {
  const source = detail.value?.element
  if (!source || dirty.value || locked.value || props.using) return
  if (comments.value && !(await comments.value.confirmLeave())) return
  if (dirty.value || locked.value || props.using || detail.value?.element.id !== source.id) return
  emit('use', { ...source })
}
async function selectImage(version: string) {
  if (version === selectedVersion.value) return
  if (comments.value && !(await comments.value.confirmLeave())) return
  selectedVersion.value = version
}
async function removeSelectedImage() {
  if (comments.value && !(await comments.value.confirmLeave())) return
  removeMedia(selectedVersion.value)
}
</script>
<template>
  <ElDialog
    :model-value="active"
    :title="elementId ? '元素详情' : '新建元素'"
    width="min(1600px, 90vw)"
    top="5dvh"
    class="element-dialog"
    :class="{ 'element-preview-expanded': previewExpanded }"
    :before-close="close"
    :close-on-click-modal="false"
    :show-close="
      !downloader.pending.value && !locked && !using && !mover?.locked && !copier?.locked
    "
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" :title="elementId ? '元素详情' : '新建元素'" hide-theme />
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
          <video v-if="previewUrl && previewKind === 'video'" :src="previewUrl" controls playsinline preload="metadata" />
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
            <button v-for="(media, index) in fields.media" :key="media.assetVersionId"
              type="button" :class="{ active: selectedVersion === media.assetVersionId }"
              :aria-label="`素材 ${index + 1}${media.isPrimary ? '，主图' : ''}`"
              :title="`素材 ${index + 1}${media.isPrimary ? ' · 主图' : ''}`"
              :aria-pressed="selectedVersion === media.assetVersionId" @click="selectImage(media.assetVersionId)">
              <ReferenceThumbnail :version-id="media.assetVersionId" fill passive allow-original />
            </button>
            <button v-if="canEdit && allowed.includes('asset:read')" type="button" class="element-add-media"
              title="添加素材" aria-label="添加素材" :disabled="downloader.pending.value || using || locked" @click="showPicker">
              <IconPlus :size="20" />
            </button>
          </div>
          <div class="element-media-actions">
            <details v-if="selectedVersion && canEdit" class="element-media-menu">
              <summary title="素材操作" aria-label="素材操作"><IconRefresh :size="22" /></summary>
              <div>
                <button type="button" :disabled="locked || using || downloader.pending.value" @click="showPicker">添加其他素材</button>
                <button type="button" :disabled="locked || using || downloader.pending.value" @click="primary(selectedVersion)">设为主图</button>
                <button type="button" :disabled="locked || using || downloader.pending.value || fields.media[0]?.assetVersionId === selectedVersion" @click="moveMedia(selectedVersion, -1)">前移</button>
                <button type="button" :disabled="locked || using || downloader.pending.value || fields.media.at(-1)?.assetVersionId === selectedVersion" @click="moveMedia(selectedVersion, 1)">后移</button>
              </div>
            </details>
            <button type="button" :title="previewExpanded ? '还原预览' : '放大预览'" :aria-label="previewExpanded ? '还原预览' : '放大预览'" @click="previewExpanded = !previewExpanded">
              <IconMinimize v-if="previewExpanded" :size="22" /><IconMaximize v-else :size="22" />
            </button>
            <button v-if="selectedVersion && canEdit" type="button" title="移除引用，不删除原素材" aria-label="移除素材引用"
              :disabled="downloader.pending.value || using || locked" @click="removeSelectedImage"><IconTrash :size="22" /></button>
          </div>
        </div>
      </section>
      <section class="element-detail-panel">
        <div v-if="detail && selectedVersion" class="element-detail-tabs" role="group" aria-label="元素详情视图">
          <Button variant="ghost" :aria-pressed="detailTab === 'info'" @click="detailTab = 'info'"
            >信息</Button
          >
          <Button
            v-if="detail && selectedVersion"
            variant="ghost"
            :aria-pressed="detailTab === 'comments'"
            @click="detailTab = 'comments'"
            >素材评论</Button
          >
        </div>
        <ElForm
          v-show="detailTab === 'info' || !detail || !selectedVersion"
          ref="form"
          :model="fields"
          :rules="rules"
          label-position="top"
          class="element-fields"
          :disabled="downloader.pending.value || using || locked || !canEdit"
        >
          <ElFormItem label="分类"
            ><ElSelect v-model="fields.category"
              ><ElOption v-for="item in categories" :key="item.value" v-bind="item" /></ElSelect
          ></ElFormItem>
          <ElFormItem label="名称" prop="name"
            ><ElInput v-model="fields.name" maxlength="200" placeholder="元素名称"
          /><small class="muted">用于展示的名称，例如：角色、场景或道具名称</small></ElFormItem>
          <ElFormItem label="版本"
            ><ElInput v-model="fields.label" maxlength="100" placeholder="例如：审核稿"
          /></ElFormItem>
          <ElFormItem label="元素 ID" prop="alias" :error="aliasError"
            ><ElInput v-model="fields.alias" maxlength="100" @input="markAliasManual"
              ><template #prepend>@</template></ElInput
            ><small v-if="elementId" class="muted">修改名称不会自动改写已有别名。</small>
            <small v-else class="muted"
              >根据名称、分类和版本建议别名；手动修改后保留你的输入。唯一性以保存结果为准。</small
            >
            <Button
              v-if="!elementId && aliasManual"
              variant="ghost"
              :disabled="locked || !canEdit"
              @click="resetAliasSuggestion"
              >重置建议</Button
            >
          </ElFormItem>
          <ElFormItem label="描述"
            ><ElInput v-model="fields.description" type="textarea" :rows="4" placeholder="描述此元素（可选）"
          /></ElFormItem>
          <ElFormItem label="负责人"
            ><ElSelect
              v-model="fields.performerId"
              clearable
              :value-on-clear="null"
              :disabled="!allowed.includes('member:read')"
              placeholder="未分配"
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
              ><ElOption v-for="item in statuses" :key="item.value" v-bind="item" /></ElSelect
          ></ElFormItem>
          <h4 class="element-properties-heading">自定义属性</h4>
          <ElFormItem
            v-for="property in properties"
            :key="property.definition.id"
            :label="property.definition.name"
          >
            <ElInput
              v-if="property.definition.valueType === 'text'"
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
            <small class="muted">定义版本 {{ property.definition.versionNo }}</small>
            <button
              v-if="canEdit && newerDefinitions[property.definition.id]"
              type="button"
              class="folder-text-button"
              :disabled="downloader.pending.value || using || locked"
              @click="adoptDefinition(property.definition.id)"
            >
              采用最新定义 v{{ newerDefinitions[property.definition.id]?.versionNo }}
            </button>
          </ElFormItem>
          <Button v-if="canEdit && allowed.includes('element:configure')" variant="ghost" class="element-add-property"
            :disabled="locked || using || downloader.pending.value" @click="propertiesOpen = true"><IconPlus :size="18" />添加自定义属性</Button>
          <p v-else-if="!properties.length" class="muted">暂无自定义属性</p>
          <p v-if="detail" class="muted">
            内部修订 #{{ detail.currentRevision.revisionNo }} · 并发版本
            {{ detail.element.revision }}
          </p>
        </ElForm>
        <div
          v-if="detail && selectedVersion"
          v-show="detailTab === 'comments'"
          class="element-comments"
        >
          <p class="muted">
            评论绑定当前选中的素材版本，独立于元素保存；切换素材会读取对应版本的评论。
          </p>
          <MediaComments
            :visible="active"
            ref="comments"
            :target="{ assetVersionId: selectedVersion }"
            :media-kind="previewKind"
          />
        </div>
      </section>
    </div>
    <PropertyDefinitionsDialog v-if="propertiesOpen" :project-id="projectId" :visible="active"
      @close="propertiesOpen = false" @changed="propertyChanged" />
    <DirectoryMoveDialog
      :visible="active"
      ref="mover"
      :project-id="projectId"
      kind="element"
      :can-create-folder="actions.includes('folder:write')"
      :allowed="canEdit && !downloader.pending.value && !locked && !dirty"
      @changed="emit('saved')"
    />
    <ElementCopyDialog
      :visible="active"
      ref="copier"
      v-if="copyOpen && detail"
      :source="detail"
      @close="copyOpen = false"
    />
    <ElementHistoryDialog
      :visible="active"
      v-if="historyOpen && elementId"
      :element-id="elementId"
      @close="historyOpen = false"
    />
    <p v-if="downloader.pending.value" role="status">
      正在读取 {{ downloader.currentName.value }} · {{ downloader.loadedBytes.value }} 字节
    </p>
    <p v-if="downloader.message.value" role="status">{{ downloader.message.value }}</p>
    <template #footer
      ><Button
        v-if="detail && actions.includes('asset:download')"
        variant="ghost"
        :disabled="downloader.pending.value || using || saving || loading || dirty"
        :title="dirty ? '请先保存修改后下载' : '下载已保存修订的全部素材'"
        @click="downloader.download([detail.element])"
        >下载元素素材</Button
      ><Button v-if="downloader.pending.value" variant="ghost" @click="downloader.stop"
        >停止下载</Button
      ><span v-if="dirty && elementId" class="muted">有未保存修改</span
      ><Button
        v-if="detail"
        variant="ghost"
        :disabled="downloader.pending.value || using || locked"
        @click="historyOpen = true"
        >历史修订</Button
      ><Button
        v-if="detail && allowed.includes('element:copy')"
        variant="ghost"
        :disabled="downloader.pending.value || using || locked"
        @click="copyOpen = true"
        >复制到项目</Button
      ><Button
        v-if="detail && actions.includes('generation:create')"
        variant="ghost"
        :disabled="downloader.pending.value || using || locked || dirty || loading"
        :title="dirty ? '请先保存修改后再使用' : '加入当前创作草稿，不发起生成'"
        @click="useElement"
        >{{ using ? '正在检查引用…' : '使用元素' }}</Button
      ><Button
        v-if="detail && canEdit"
        variant="ghost"
        :disabled="downloader.pending.value || using || locked || dirty || loading"
        :title="dirty ? '请先保存修改后再移动' : '移动到项目元素目录'"
        @click="mover?.open(detail.element)"
        >移动到目录</Button
      ><Button
        v-if="canRemove"
        variant="ghost"
        :disabled="downloader.pending.value || using || locked || conflict"
        @click="remove"
        >删除元素</Button
      ><Button
        variant="ghost"
        :disabled="downloader.pending.value || using || locked"
        @click="close"
        >{{ elementId ? '关闭' : '取消' }}</Button
      ><Button
        v-if="canEdit && !uncertain"
        :disabled="downloader.pending.value || using || saving || loading || conflict"
        @click="save"
        >{{ saving ? '保存中…' : elementId ? '保存' : '创建' }}</Button
      ><Button v-if="uncertain" :disabled="saving || loading || using" @click="retry">{{
        saving ? '正在确认…' : '重试确认原请求'
      }}</Button></template
    >
    <ElDialog
      v-model="pickerOpen"
      title="选择项目素材"
      width="min(760px, 92vw)"
      append-to-body
      :close-on-click-modal="false"
    >
      <template #header="{ titleId, titleClass }">
        <DialogHeading :title-id="titleId" :title-class="titleClass" title="选择项目素材" />
      </template>
      <div class="element-toolbar">
        <ElSelect v-model="pickerKind" aria-label="素材类型" style="width:110px"><ElOption label="图片" value="image" /><ElOption label="视频" value="video" /></ElSelect>
        <ElInput
          v-model="pickerSearch"
          placeholder="搜索项目素材"
          clearable
          @keyup.enter="searchCandidates"
          @clear="searchCandidates"
        /><Button variant="ghost" @click="searchCandidates">搜索</Button>
      </div>
      <p v-if="pickerLoading" role="status">正在加载素材…</p>
      <p v-if="pickerError" class="project-error" role="alert">{{ pickerError }}</p>
      <div v-for="entry in candidates" :key="entry.id" class="element-picker-row">
        <IconPhoto :size="24" /><span
          >{{ entry.name
          }}<small class="muted">
            · {{ entry.asset.file.width }} × {{ entry.asset.file.height }}</small
          ></span
        ><Button
          variant="ghost"
          :disabled="
            fields.media.some((media) => media.assetVersionId === entry.asset.currentVersionId)
          "
          @click="addMedia(entry.asset)"
          >{{
            fields.media.some((media) => media.assetVersionId === entry.asset.currentVersionId)
              ? '已选择'
              : '添加'
          }}</Button
        >
      </div>
      <p v-if="!pickerLoading && !candidates.length" class="muted">
        暂无匹配素材，请先到素材目录上传。
      </p>
      <ElPagination
        v-if="pickerTotal > 30"
        v-model:current-page="pickerPage"
        :page-size="30"
        :total="pickerTotal"
        layout="prev, pager, next"
      />
      <template #footer><Button @click="pickerOpen = false">完成选择</Button></template>
    </ElDialog>
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

