<script setup lang="ts">
import { ElButton, ElDialog, ElPopover, ElInput, ElOption, ElPagination, ElSelect, ElMessageBox } from 'element-plus'

import { reactive, shallowRef, watch, onBeforeUnmount } from 'vue'
import { IconFolder, IconChevronDown, IconSearch, IconSortDescending, IconCrop, IconPlus, IconCheck, IconMaximize, IconTrash, IconPlayerPlay, IconAdjustments, IconX, IconAt, IconUser, IconMountain, IconBox } from '@tabler/icons-vue'
import type { DraftReference, ModelCapability } from '@/api/creation'
import type { ReferenceCandidate } from '@/api/references'
import ElementEditor from './ElementEditor.vue'
import { useReferenceElementCreate } from '@/composables/useReferenceElementCreate'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { useReferenceAssetDelete } from '@/composables/useReferenceAssetDelete'
import { useReferencePreview } from '@/composables/useReferencePreview'
import { usePickerElementCopy } from '@/composables/usePickerElementCopy'
import { useReferenceScopeLabel } from '@/composables/useReferenceScopeLabel'
import { useReferencePicker } from '@/composables/useReferencePicker'
import { useReferenceUpdates } from '@/composables/useReferenceUpdates'
import { selectCandidate, moveReference, compatibleReferenceRoles, selectReferenceMedia } from '@/utils/draftReferences'
import ReferenceCropDialog from './ReferenceCropDialog.vue'
import ReferenceUploads from './ReferenceUploads.vue'
import ReferenceThumbnail from './ReferenceThumbnail.vue'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{
  projectId: string
  folderId?: string | null
  disabled: boolean
  protectedKeys: string[]
  model?: ModelCapability | null
}>()
const emit = defineEmits<{ uploaded: []; pickerOpen: [value: boolean] }>()
const references = defineModel<DraftReference[]>({ required: true })
const revisionUpdates = useReferenceUpdates(() => props.projectId, references, () => props.disabled, () => props.model)
const firstForKey = (index: number) => references.value.findIndex(item => item.referenceKey === references.value[index]?.referenceKey) === index
function upgrade(key: string) {
  void revisionUpdates.upgrade(key, message => ElMessageBox.confirm(message, '确认升级元素引用', {
    confirmButtonText: '替换为新修订图片', cancelButtonText: '保留原引用', type: 'warning',
  }).then(() => true).catch(() => false))
}
const { elementScope, mediaType, category, source, recent, sort, open, q, kind, rows, page, total, loading, error, load, search, show: openPicker, close, canSelect, contextRevision } =
  useReferencePicker(() => props.projectId, () => props.disabled, () => props.folderId ?? null)
const elementCopy = usePickerElementCopy(() => props.projectId)
const scopeLabel = useReferenceScopeLabel(() => props.projectId, () => props.folderId ?? null, () => open.value)
const copiedCandidates = reactive<Record<string, ReferenceCandidate>>({})
watch(contextRevision, () => { for (const key of Object.keys(copiedCandidates)) delete copiedCandidates[key] })
function changeScope(value: 'mine' | 'project') { elementScope.value = value; search() }
const newElement = useReferenceElementCreate(() => props.projectId, () => open.value && !props.disabled)
watch(open, value => emit('pickerOpen', value), { flush: 'sync' })
const preview = useReferencePreview(() => open.value && !props.disabled)
const deletion = useReferenceAssetDelete(props.projectId, () => open.value && !props.disabled, canSelect, () => { preview.close(); search(); emit('uploaded') })
const cropSource = shallowRef<ReferenceCandidate | null>(null)
function showCrop(row: ReferenceCandidate) {
  if (canSelect(row) && row.kind === 'asset' && !row.allowedMediaRoles.includes('reference_video')) cropSource.value = row
}
function cropped() {
  cropSource.value = null
  kind.value = 'asset'; source.value = 'uploaded'; mediaType.value = ''; recent.value = false; sort.value = 'newest'; q.value = ''
  search(); emit('uploaded')
}
watch(contextRevision, () => { cropSource.value = null })
const roles = reactive<Record<string, string>>({})
const mediaSelections = reactive<Record<string, string[]>>({})
watch(contextRevision, () => {
  for (const key of Object.keys(roles)) delete roles[key]
  for (const key of Object.keys(mediaSelections)) delete mediaSelections[key]
}, { flush: 'sync' })
const mediaIdentity = (row: ReferenceCandidate) => `${identity(row)}:${row.elementRevisionId}`
const selectedMedia = (row: ReferenceCandidate) => mediaSelections[mediaIdentity(row)] ?? [row.primaryAssetVersionId || row.assetVersionIds[0]!]
function toggleMedia(row: ReferenceCandidate, id: string, checked: boolean) {
  if (props.disabled) return
  const chosen = selectedMedia(row).filter(value => value !== id)
  mediaSelections[mediaIdentity(row)] = checked ? [...chosen, id] : chosen
}
const labels: Record<string, string> = {
  reference_image: '参考图',
  first_frame: '首帧',
  reference_video: '参考视频',
}
const identity = (row: ReferenceCandidate) => `${row.kind}:${row.id}`
const options = (row: ReferenceCandidate) => compatibleReferenceRoles(row, props.model)
function selectedRole(row: ReferenceCandidate) {
  const available = options(row)
  return available.includes(roles[identity(row)] || '') ? roles[identity(row)] : available[0]
}
function uploaded() {
  emit('uploaded')
  if (!open.value || props.disabled) return
  kind.value = 'asset'
  q.value = ''
  search()
}
async function add(row: ReferenceCandidate) {
  if (!canSelect(row) || elementCopy.pending.value) return
  const role = selectedRole(row)
  if (!role || !options(row).includes(role)) return
  try {
    const snapshot = JSON.stringify(references.value), revision = contextRevision.value
    const resolved = copiedCandidates[mediaIdentity(row)] || await elementCopy.resolve(row)
    if (!resolved || !canSelect(row) || contextRevision.value !== revision || JSON.stringify(references.value) !== snapshot) return
    copiedCandidates[mediaIdentity(row)] = resolved
    const media = selectedMedia(row).map(id => resolved.assetVersionIds[row.assetVersionIds.indexOf(id)]).filter((id): id is string => !!id)
    const candidate = role === 'reference_image' ? selectReferenceMedia(resolved, media) : resolved
    references.value = selectCandidate(references.value, candidate, role, props.model, props.protectedKeys)
    error.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '添加引用失败'
  }
}
function remove(index: number) {
  const item = references.value[index]
  if (!item || props.disabled || props.protectedKeys.includes(item.referenceKey)) return
  references.value = references.value
    .filter((_, position) => position !== index)
    .map((value, ordinal) => ({ ...value, ordinal }))
}
function move(index: number, offset: number) {
  if (!props.disabled) references.value = moveReference(references.value, index, offset)
}
const anchor = shallowRef<HTMLElement>()
const popover = shallowRef<InstanceType<typeof ElPopover>>()
let anchorObserver: ResizeObserver | undefined
watch(anchor, target => {
  anchorObserver?.disconnect()
  if (!target) return
  anchorObserver = new ResizeObserver(() => popover.value?.popperRef?.popperInstanceRef?.update())
  anchorObserver.observe(target)
}, { flush: 'post' })
onBeforeUnmount(() => anchorObserver?.disconnect())
function show(tabKind?: 'asset' | 'element', target?: HTMLElement) {
  if (target) anchor.value = target
  if (open.value && kind.value === tabKind) { close(); return }
  mediaType.value = ''; recent.value = false
  if (tabKind === 'asset') source.value = 'uploaded'
  openPicker(tabKind)
}
function switchTab(tab: 'asset' | 'element' | 'generated') {
  kind.value = tab === 'element' ? 'element' : 'asset'
  source.value = tab === 'generated' ? 'generated' : tab === 'asset' ? 'uploaded' : ''
  mediaType.value = ''; recent.value = false
  search()
}
function filterMedia(value: '' | 'image' | 'video' | 'recent') {
  recent.value = value === 'recent'
  mediaType.value = value === 'recent' ? '' : value
  search()
}
function isSelected(row: ReferenceCandidate) {
  row = copiedCandidates[mediaIdentity(row)] || row
  return references.value.some(item => item.elementRevisionId === (row.elementRevisionId || null) && row.assetVersionIds.includes(item.assetVersionId))
}
function toggleCandidate(row: ReferenceCandidate) {
  if (!canSelect(row) || elementCopy.pending.value) return
  if (!isSelected(row)) { add(row); return }
  row = copiedCandidates[mediaIdentity(row)] || row
  const matches = references.value.filter(item => item.elementRevisionId === (row.elementRevisionId || null) && row.assetVersionIds.includes(item.assetVersionId))
  if (matches.some(item => props.protectedKeys.includes(item.referenceKey))) {
    error.value = '提示词仍提及此引用，请先编辑提示词'
    return
  }
  references.value = references.value.filter(item => !matches.includes(item)).map((item, ordinal) => ({ ...item, ordinal }))
}
const categories = [
  { value: '', label: '全部', icon: IconAt },
  { value: 'character', label: '角色', icon: IconUser },
  { value: 'scene', label: '场景', icon: IconMountain },
  { value: 'prop', label: '道具', icon: IconBox },
  { value: 'other', label: '其他', icon: IconBox },
] as const
defineExpose({ show })
</script>

<template>
  <section class="draft-references">
    <div class="reference-heading">
      <h3>
        参考素材 <span>{{ references.length }}/200</span>
      </h3>
      <Button type="button" variant="outline" :disabled="disabled" @click="show('asset', $event.currentTarget as HTMLElement)"
        >添加素材 / 元素</Button
      >
    </div>
    <p v-if="!references.length" class="muted">
      可选择项目内有引用权限的素材或元素；保存后固定为当前版本。
    </p>
    <p v-if="revisionUpdates.loading.value" class="muted">正在检查元素修订，当前引用保持不变…</p>
    <p v-if="revisionUpdates.error.value" role="alert">{{ revisionUpdates.error.value }}</p>
    <Button v-if="references.some(item => item.elementRevisionId)" variant="ghost" :disabled="disabled || revisionUpdates.loading.value" @click="revisionUpdates.check">检查元素更新</Button>
    <ul>
      <li
        v-for="(item, index) in references"
        :key="`${item.referenceKey}:${item.assetVersionId}:${item.mediaRole}`"
      >
        <ReferenceThumbnail
          v-if="['reference_image', 'first_frame'].includes(item.mediaRole)"
          :version-id="item.assetVersionId"
        />
        <span
          >{{ index + 1 }} · {{ labels[item.mediaRole] || item.mediaRole }} · 素材版本
          {{ item.assetVersionId
          }}<small v-if="item.elementRevisionId">
            · 元素修订 {{ item.elementRevisionId }}</small
          ></span
        >
        <div v-if="item.elementRevisionId && firstForKey(index) && revisionUpdates.updates.value[item.elementRevisionId]?.state === 'updated'" class="reference-upgrade">
          <p>元素已有新修订 {{ revisionUpdates.updates.value[item.elementRevisionId]?.candidate?.elementRevisionId }}，当前仍使用旧修订。</p>
          <ReferenceThumbnail v-for="id in revisionUpdates.updates.value[item.elementRevisionId]?.candidate?.assetVersionIds" :key="id" :version-id="id" />
          <Button variant="ghost" :disabled="disabled" @click="upgrade(item.referenceKey)">检查并升级此引用</Button>
        </div>
        <p v-if="item.elementRevisionId && firstForKey(index) && revisionUpdates.updates.value[item.elementRevisionId]?.state === 'unavailable'" class="muted">无法确认此元素的新修订是否可用，旧引用保留；保存及提交时仍会重新校验权限。</p>
        <div>
          <el-button text :disabled="disabled || index === 0" @click="move(index, -1)"
            >上移</el-button
          ><el-button
            text
            :disabled="disabled || index === references.length - 1"
            @click="move(index, 1)"
            >下移</el-button
          ><el-button
            text
            :disabled="disabled || protectedKeys.includes(item.referenceKey)"
            :title="
              protectedKeys.includes(item.referenceKey)
                ? '提示词仍提及此引用，请先编辑提示词'
                : '移除引用'
            "
            @click="remove(index)"
            >移除</el-button
          >
        </div>
      </li>
    </ul>
    <ElPopover ref="popover" :visible="open" :virtual-ref="anchor" virtual-triggering placement="top-start" :width="800" :show-arrow="false" popper-class="creation-reference-popover" :popper-options="{ modifiers: [{ name: 'flip', options: { fallbackPlacements: ['bottom-start', 'top-end'] } }] }">
      <section class="reference-picker-panel" role="dialog" aria-label="选择参考素材" @keydown.esc.stop="close">
      <header class="reference-picker-tabs">
        <button type="button" :aria-pressed="kind !== 'element' && source !== 'generated'" @click="switchTab('asset')">上传素材</button>
        <button type="button" :aria-pressed="kind === 'element'" @click="switchTab('element')">元素</button>
        <button type="button" :aria-pressed="kind !== 'element' && source === 'generated'" title="已归档到项目素材库的生成结果" @click="switchTab('generated')">生成素材</button>
        <button type="button" class="reference-picker-close" aria-label="关闭素材面板" @click="close"><IconX :size="18" /></button>
      </header>
      <div class="reference-picker-surface">
        <div class="reference-picker-filters">
          <template v-if="kind !== 'element'">
            <button :aria-pressed="recent" title="最近七天添加的素材" @click="filterMedia('recent')">最近</button>
            <button :aria-pressed="!recent && !mediaType" @click="filterMedia('')">全部</button>
            <button :aria-pressed="mediaType === 'image'" @click="filterMedia('image')">图片</button>
            <button :aria-pressed="mediaType === 'video'" @click="filterMedia('video')">视频</button>
          </template>
          <ElPopover v-else trigger="click" placement="bottom-start" :width="260">
            <template #reference><button class="reference-scope-trigger" aria-label="选择元素范围"><IconAt v-if="elementScope === 'mine'" :size="20" /><IconFolder v-else :size="20" /><span>{{ elementScope === 'mine' ? '我的元素' : scopeLabel.projectName.value }}</span><IconChevronDown :size="12" /></button></template>
            <div class="reference-scope-menu"><button :aria-pressed="elementScope === 'mine'" @click="changeScope('mine')"><IconAt :size="20" />我的元素</button><button :aria-pressed="elementScope === 'project'" @click="changeScope('project')"><IconFolder :size="20" />{{ scopeLabel.projectName.value }}</button></div>
          </ElPopover>
          <ElPopover trigger="click" placement="bottom-end" :width="260">
            <template #reference><button class="reference-sort-trigger" type="button" aria-label="排序与搜索"><IconSortDescending :size="16" />{{ kind === 'element' ? '筛选' : '排序' }}</button></template>
            <div class="reference-sort-menu">
              <ElSelect v-if="elementScope !== 'mine' || kind !== 'element'" v-model="sort" aria-label="素材排序" @change="search"><ElOption label="最新优先" value="newest" /><ElOption label="最早优先" value="oldest" /><ElOption label="名称排序" value="name" /></ElSelect>
              <ElInput v-model="q" placeholder="搜索名称" aria-label="搜索素材或元素名称" clearable @keyup.enter="search" @clear="search" />
              <Button variant="ghost" :disabled="loading" @click="search">搜索</Button>
            </div>
          </ElPopover>
          <ElPopover v-if="kind === 'element'" trigger="click" placement="bottom-end" :width="260"><template #reference><button aria-label="搜索元素"><IconSearch :size="17" /></button></template><ElInput v-model="q" placeholder="搜索元素名称" clearable @keyup.enter="search" @clear="search" /></ElPopover>
        </div>
        <div class="reference-picker-body" :class="{ 'has-categories': kind === 'element' }">
          <nav v-if="kind === 'element'" class="reference-categories" aria-label="元素分类">
            <button v-for="item in categories" :key="item.value" :aria-pressed="category === item.value" @click="category = item.value; search()"><component :is="item.icon" :size="17" />{{ item.label }}</button>
          </nav>
      <div class="reference-picker-content">
      <p v-if="error" class="project-error" role="alert">{{ error }}</p>
      <p v-if="deletion.error.value || deletion.actions.error.value" class="project-error" role="alert">{{ deletion.error.value || deletion.actions.error.value }}</p>
      <p v-if="deletion.actions.lifecycleUncertain.value" role="status">删除结果尚未确认。<Button :disabled="deletion.actions.pending.value" @click="deletion.actions.retryLifecycle">重试确认</Button></p>
      <p v-if="elementCopy.pending.value" role="status">正在复制元素到当前项目…</p><p v-if="elementCopy.error.value" class="project-error" role="alert">{{ elementCopy.error.value }}</p>
      <p v-if="loading" role="status">正在读取可引用内容…</p>
      <p v-if="newElement.error.value" class="project-error" role="alert">{{ newElement.error.value }}</p>
      <ul class="reference-candidates">
        <li v-if="kind === 'element'"><button class="reference-new-element" :disabled="disabled || newElement.loading.value" @click="newElement.show"><span class="reference-new-element-icon"><IconPlus :size="24" /></span>新建元素</button></li>
        <li v-show="kind !== 'element' && source !== 'generated'" class="reference-upload-cell"><ReferenceUploads :project-id="projectId" :folder-id="folderId ?? null" :disabled="disabled || !open" compact @uploaded="uploaded" /></li>
        <li v-for="row in rows" :key="identity(row)" class="reference-candidate" :class="{ selected: isSelected(row), 'empty-element': !row.assetVersionIds.length }">
          <div class="reference-candidate-media">
            <button type="button" class="reference-candidate-select" :aria-label="`选择引用 ${row.displayName}`" :aria-pressed="isSelected(row)" :disabled="disabled || elementCopy.pending.value || (!isSelected(row) && !options(row).length)" @click="toggleCandidate(row)">
              <ReferenceThumbnail v-if="row.primaryAssetVersionId || row.assetVersionIds[0]" :version-id="row.primaryAssetVersionId || row.assetVersionIds[0]!" :alt="row.displayName" :allow-original="!row.allowedMediaRoles.includes('reference_video') && Number(row.byteSize || 0) > 0 && Number(row.byteSize) <= 20 * 1024 * 1024" fill passive />
              <span v-if="!row.assetVersionIds.length" class="reference-no-image">暂无元素图片</span>
              <IconPlayerPlay v-if="row.allowedMediaRoles.includes('reference_video')" class="reference-video-mark" :size="28" />
              <span class="reference-candidate-check"><IconCheck v-if="isSelected(row)" :size="16" /></span>
            </button>
            <div v-if="row.assetVersionIds.length" class="reference-candidate-tools">
              <button type="button" :aria-label="`预览 ${row.displayName}`" title="预览" @click="preview.show(row)"><IconMaximize :size="16" /></button>
              <button v-if="row.kind === 'asset' && !row.allowedMediaRoles.includes('reference_video')" type="button" :aria-label="`裁剪 ${row.displayName}`" title="裁剪后新增素材" :disabled="disabled" @click="showCrop(row)"><IconCrop :size="16" /></button>
              <ElPopover v-if="row.kind === 'element' || (model && options(row).length > 1)" trigger="click" placement="right" :width="260" :show-arrow="false">
                <template #reference><button type="button" :aria-label="`引用设置 ${row.displayName}`" title="选择引用角色与元素图片"><IconAdjustments :size="16" /></button></template>
                <strong>{{ categories.find(item => item.value === row.category)?.label || '元素' }} · {{ row.displayName }}</strong>
          <span v-if="row.kind === 'element'" class="reference-candidate-alias" :title="row.alias || ''">@{{ row.alias }}</span>
                <ElSelect :model-value="selectedRole(row)" :disabled="!options(row).length" aria-label="引用角色" @update:model-value="(value: string) => (roles[identity(row)] = value)"><ElOption v-for="role in options(row)" :key="role" :label="labels[role] || role" :value="role" /></ElSelect>
                <div v-if="row.kind === 'element' && selectedRole(row) === 'reference_image'" class="reference-media-options">
                  <label v-for="id in row.assetVersionIds" :key="id"><input type="checkbox" :checked="selectedMedia(row).includes(id)" :disabled="disabled" :aria-label="`选择素材版本 ${id}`" @change="toggleMedia(row, id, ($event.target as HTMLInputElement).checked)" /><ReferenceThumbnail :version-id="id" /><span>{{ id === row.primaryAssetVersionId ? '主图' : '附图' }}</span></label>
                </div>
                <Button :disabled="disabled || !options(row).length" @click="add(row)">加入引用</Button>
              </ElPopover>
              <button v-if="row.kind === 'asset'" type="button" :aria-label="`删除素材 ${row.displayName}`" title="将原素材移入回收站" :disabled="disabled || deletion.checking.value || deletion.actions.actionsLocked.value" @click="deletion.remove(row)"><IconTrash :size="16" /></button>
            </div>
          </div>
          <strong v-if="row.kind === 'element'" class="reference-candidate-name" :title="row.displayName">{{ categories.find(item => item.value === row.category)?.label || '元素' }} · {{ row.displayName }}</strong>
          <span v-if="row.kind === 'element'" class="reference-candidate-alias" :title="row.alias || ''">@{{ row.alias }}</span>
        </li>
      </ul>
      <p v-if="!loading && !rows.length" class="muted reference-picker-empty">暂无可引用的匹配内容。</p>
      <el-pagination
        v-if="total > 12"
        v-model:current-page="page"
        :page-size="12"
        :total="total"
        layout="prev,pager,next"
        @current-change="load"
      />
      </div>
        </div>
      </div>
      </section>
    </ElPopover>
    <ReferenceCropDialog v-if="cropSource" :candidate="cropSource" :project-id="projectId" :folder-id="folderId ?? null" :visible="open && !disabled" @close="cropSource = null" @saved="cropped" />
    <Teleport to="body"><ElementEditor v-if="newElement.open.value" :project-id="projectId" :element-id="null" :actions="newElement.actions.value" :visible="open" @close="newElement.open.value = false" @saved="newElement.open.value = false; search(); emit('uploaded')" /></Teleport>
    <ElDialog :model-value="Boolean(preview.candidate.value)" width="min(1000px, 94vw)" append-to-body :before-close="preview.close" :close-on-click-modal="false">
      <template #header="{ titleId, titleClass }"><DialogHeading :title-id="titleId" :title-class="titleClass" :title="preview.candidate.value?.displayName || '参考素材预览'" /></template>
      <p v-if="preview.loading.value" role="status">正在读取预览…</p>
      <p v-if="preview.error.value" class="project-error" role="alert">{{ preview.error.value }}</p>
      <video v-if="preview.url.value && preview.candidate.value?.allowedMediaRoles.includes('reference_video')" :src="preview.url.value" controls class="reference-full-preview" />
      <img v-else-if="preview.url.value" :src="preview.url.value" :alt="preview.candidate.value?.displayName" class="reference-full-preview" />
    </ElDialog>
  </section>
</template>
<style>
.creation-reference-popover.el-popover { --picker-shell:#f0f1ef; --picker-surface:#fafaf9; --picker-tile:#e8e9e7; --picker-line:#dedfdd; --picker-muted:#777b76; padding:0; max-width:calc(100vw - 24px); border-radius:24px 24px 20px 20px; background:var(--picker-shell); color:var(--foreground); border:0; box-shadow:0 3px 0 var(--picker-shell),0 16px 48px #0003; }
.dark .creation-reference-popover.el-popover { --picker-shell:#1d1f20; --picker-surface:#262829; --picker-tile:#303233; --picker-line:#363839; --picker-muted:#909192; }
</style>
<style scoped>
.reference-new-element { font-weight:600; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; width: 100%; aspect-ratio: 1; border: 1px dashed var(--border); border-radius: 12px; color: var(--foreground); background: var(--picker-tile); cursor: pointer; }
.reference-new-element-icon { display:grid; place-items:center; width:44px; height:44px; border-radius:50%; border:1px solid var(--picker-muted); background:radial-gradient(circle at 50% 25%, var(--picker-muted), var(--picker-tile)); box-shadow:inset 0 0 5px #fff3; }
.reference-scope-trigger { display:flex; align-items:center; gap:8px; max-width:70%; }
.reference-scope-trigger span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.reference-scope-menu { display:grid; gap:4px; }
.reference-scope-menu button { display:flex; align-items:center; gap:10px; padding:10px; border:0; border-radius:9px; text-align:left; color:var(--foreground); background:transparent; cursor:pointer; }
.reference-scope-menu button:hover, .reference-scope-menu button[aria-pressed="true"] { background:var(--muted); }
.reference-candidate-alias { display:block; margin:4px 8px 0; font-size:12px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.reference-no-image { color:var(--picker-muted); font-size:12px; }
.empty-element .reference-candidate-name, .empty-element .reference-candidate-alias { opacity:.4; }
.reference-full-preview { display: block; width: 100%; height: 65vh; object-fit: contain; }
.reference-picker-panel { height: min(598px, 70dvh); display: flex; flex-direction: column; font-size:12px; }
.reference-picker-tabs { display: flex; align-items: center; gap: 4px; padding: 12px; flex-shrink: 0; }
.reference-picker-tabs button { height:32px; padding: 0 13px; border: 0; border-radius: 999px; background: transparent; color: var(--picker-muted); cursor: pointer; font-size:12px; font-weight: 600; }
.reference-picker-tabs button[aria-pressed="true"] { color: var(--background); background: var(--foreground); }
.reference-picker-tabs .reference-picker-close { display: grid; place-items: center; margin-left: auto; width:32px; padding: 8px; background: var(--picker-surface); color:var(--foreground); }
.reference-picker-surface { display: flex; flex: 1; flex-direction: column; min-height: 0; margin: 0 4px 4px; background: var(--picker-surface); border-radius: 18px; overflow: hidden; }
.reference-picker-filters { display: flex; align-items: center; gap: 4px; height:49px; padding: 8px 10px; border-bottom: 1px solid var(--picker-shell); flex-shrink: 0; }
.reference-picker-filters > button { height:32px; border: 0; border-radius: 999px; padding: 7px 12px; background: transparent; color: var(--picker-muted); cursor: pointer; font-size:12px; font-weight:600; }
.reference-picker-filters > button[aria-pressed="true"] { background: var(--picker-tile); color: var(--foreground); box-shadow: inset 0 0 0 1px var(--picker-line); }
.reference-picker-filters .reference-sort-trigger { margin-left:auto; display:flex; align-items:center; gap:7px; font-size:14px; }
.reference-sort-menu { display:grid; gap:10px; }
.reference-sort { width: 120px; margin-left: auto; }
.reference-query { width: 140px; }
.reference-picker-body { display: grid; grid-template-columns: minmax(0, 1fr); min-height: 0; flex: 1; }
.reference-picker-body.has-categories { grid-template-columns: 160px minmax(0, 1fr); }
.reference-categories { padding: 12px 8px; }
.reference-categories button { display: flex; width: 100%; align-items: center; gap: 10px; padding: 7px 8px; border: 0; border-radius: 8px; color: var(--foreground); background: transparent; cursor: pointer; text-align: left; }
.reference-categories button[aria-pressed="true"] { background: var(--picker-tile); }
.reference-picker-content { overflow: auto; padding: 14px; min-height: 0; }
.reference-candidates { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px 12px; margin: 0; }
.has-categories .reference-candidates { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.reference-candidates li { display: block; min-width: 0; padding: 0; border: 0; }
.reference-candidate-media { position: relative; aspect-ratio: 1; border-radius: 11px; background: var(--picker-tile); }
.reference-candidate-media :deep(.reference-thumbnail) { background:var(--picker-tile); }
.reference-candidate-select { display: block; width: 100%; height: 100%; padding: 0; border: 1px solid transparent; border-radius: inherit; background: transparent; color: var(--foreground); cursor: pointer; overflow: hidden; }
.reference-candidate.selected .reference-candidate-media { outline:1.5px solid var(--primary); outline-offset:2px; }
.reference-candidate.selected :deep(.reference-thumbnail img) { filter:brightness(.65); }
.reference-candidate-check { position: absolute; top: 10px; left: 10px; display: grid; place-items: center; width: 20px; height: 20px; border: 1px solid var(--border); border-radius: 6px; opacity: 0; background: var(--surface); }
.reference-candidate.selected .reference-candidate-check { opacity: 1; background: var(--primary); color: var(--primary-foreground); border-color: var(--primary); }
.reference-candidate:hover .reference-candidate-check, .reference-candidate:focus-within .reference-candidate-check { opacity: 1; }
.reference-candidate-tools { position: absolute; top: 8px; right: 8px; display: flex; flex-direction: column; gap: 4px; opacity: 0; }
.reference-candidate:hover .reference-candidate-tools, .reference-candidate:focus-within .reference-candidate-tools { opacity: 1; }
.reference-candidate-tools button { display: grid; place-items: center; width: 24px; height: 24px; border:0; border-radius: 50%; background: var(--picker-surface); color: var(--foreground); cursor: pointer; }
.reference-candidate-name { display: block; margin: 8px 8px 0; font-size: 12px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted-foreground); }
.reference-video-mark { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); color: white; filter: drop-shadow(0 1px 3px #000); pointer-events: none; }
.reference-picker-content > .project-error { padding: 8px; margin: 0 0 8px; }
.reference-picker-empty { padding: 16px 0; }
.reference-picker-panel button:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.reference-picker-panel button:disabled { cursor: not-allowed; opacity: .45; }
@media (max-width: 640px) {
  .reference-candidates, .has-categories .reference-candidates { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .reference-picker-body.has-categories { grid-template-columns: 100px minmax(0, 1fr); }
  .reference-picker-filters { flex-wrap: wrap; }
  .reference-query { flex: 1; }
}

.draft-references {
  margin: 16px 0;
  border-top: 1px solid var(--border);
  padding-top: 16px;
}
.reference-heading,
.reference-search {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: space-between;
}
.reference-heading h3 {
  font-size: 14px;
}
.reference-upgrade {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--muted);
}
.reference-media-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.reference-media-options label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.reference-media-options input { accent-color: var(--primary); }
.reference-upgrade p {
  width: 100%;
  margin: 0;
  overflow-wrap: anywhere;
}
.reference-heading span {
  color: var(--muted-foreground);
}
ul {
  list-style: none;
  padding: 0;
}
li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.reference-search .el-select {
  width: 120px;
  flex-shrink: 0;
}
.reference-search > button {
  flex-shrink: 0;
  white-space: nowrap;
}
.reference-candidates .el-select {
  width: 130px;
  flex-shrink: 0;
}
.reference-candidates li > div:first-child {
  flex: 1 0 100%;
  min-width: 0;
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  li {
    flex-wrap: wrap;
  }
  .reference-search {
    flex-wrap: wrap;
  }
}
</style>
