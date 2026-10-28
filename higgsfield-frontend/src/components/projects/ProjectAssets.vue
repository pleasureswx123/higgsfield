<script setup lang="ts">
import { useAssetBatchStatus } from '@/composables/useAssetBatchStatus'
import { assetStatuses, assetStatus } from '@/utils/assetStatus'
import AssetHoverVideo from './AssetHoverVideo.vue'
import ElementEditor from './ElementEditor.vue'
import AssetCardMenu from './AssetCardMenu.vue'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ref, toRef, watch, computed } from 'vue'
import {
  ElDialog,
  ElPopover,
  ElInput,
  ElSelect,
  ElOption,
  ElPagination,
  ElForm,
  ElFormItem,
  ElCheckbox,
  ElInputNumber,
  ElDatePicker,
} from 'element-plus'
import { IconX, IconChevronRight, IconCircleDotted, IconMaximize, IconCheckbox, IconAt, IconPencil, IconFolderSymlink, IconFolderPlus, IconTrash, IconDownload, IconCloud, IconEye, IconPhoto, IconMovie, IconUpload, IconFileText, IconFilter, IconLayoutGrid, IconDots, IconRefresh, IconSearch } from '@tabler/icons-vue'
import { assetAccept, documentFormats } from '@/utils/assetFormats'
import type { Asset } from '@/api/assets'
import Button from '@/components/ui/Button.vue'
import { useAssetLibrary } from '@/composables/useAssetLibrary'
import { useAssetUploads } from '@/composables/useAssetUploads'
import { useAssetActions } from '@/composables/useAssetActions'
import { useContentSelection } from '@/composables/useContentSelection'
import { useAssetBatchDownload } from '@/composables/useAssetBatchDownload'
import { useAssetBatchDelete } from '@/composables/useAssetBatchDelete'
import { useAssetBatchRestore } from '@/composables/useAssetBatchRestore'
import AssetUploadPanel from './AssetUploadPanel.vue'
import ReferenceThumbnail from './ReferenceThumbnail.vue'
import FavoriteButton from './FavoriteButton.vue'
import MediaComments from './MediaComments.vue'
import LibraryViewPreference from './LibraryViewPreference.vue'
import AssetPdfPreview from './AssetPdfPreview.vue'
import DirectoryMoveDialog from './DirectoryMoveDialog.vue'
const mover = ref<InstanceType<typeof DirectoryMoveDialog>>()
const copier = ref<InstanceType<typeof DirectoryMoveDialog>>()
const elementSource = ref<Asset | null>(null)
const canCreateElement = computed(() => props.projectActions?.includes('element:create') && props.projectActions?.includes('asset:reference'))
const canCopy = computed(() => props.canMove && props.projectActions?.includes('asset:create') && props.projectActions?.includes('asset:reference'))
import type { LibraryViewSettings, FolderViewSettings } from '@/api/viewPreferences'
import { groupContentByDate, contentCardWidth } from '@/utils/contentView'
const comments = ref<InstanceType<typeof MediaComments>>()
async function closeMediaPreview() {
  if (comments.value && !(await comments.value.confirmLeave())) return
  closePreview()
}
import { formatProjectDate } from '@/utils/projects'
import '@/styles/assets.css'
const props = defineProps<{
  projectActions?: string[]
  compact?: boolean
  projectId: string
  visible?: boolean
  folderId: string | null
  canUpload: boolean
  canDownload: boolean
  canMove: boolean
  canGenerate?: boolean
  refreshKey: number
  folderSettings: FolderViewSettings
}>()
const emit = defineEmits<{ restoreFolders: [settings: FolderViewSettings]; create: []; selectionChange: [count: number] }>()
const {
  rows,
  total,
  page,
  search,
  fileType,
  dates,
  includeDescendants,
  activity,
  loading,
  error,
  refresh,
  filter,
  clearFilter,
  lastViewedId,
  selected,
  mediaUrl,
  documentSections,
  pdfBlob,
  mediaError,
  mediaLoading,
  loadedBytes,
  openMedia,
  closePreview,
} = useAssetLibrary(props.projectId, toRef(props, 'folderId'), () => props.visible !== false)
const layout = ref<'square' | 'masonry'>('square'), cardSize = ref(4), splitByDate = ref(false)
const viewSettings = computed<LibraryViewSettings>(() => ({ ...props.folderSettings, layout: layout.value, cardSize: cardSize.value, splitByDate: splitByDate.value, fileType: fileType.value || null, activity: activity.value || null, dates: dates.value?.length ? [...dates.value] : null, includeDescendants: includeDescendants.value }))
const dateGroups = computed(() => groupContentByDate(rows.value, splitByDate.value))
const activeFilters = computed(() => {
  const values: { key: 'search' | 'fileType' | 'activity' | 'dates' | 'includeDescendants'; label: string }[] = []
  if (search.value.trim()) values.push({ key: 'search', label: `名称：${search.value.trim()}` })
  if (fileType.value) values.push({ key: 'fileType', label: `类型：${fileType.value === 'image' ? '图片' : fileType.value === 'video' ? '视频' : fileType.value.toUpperCase()}` })
  const activityNames = { generated: '生成来源', uploaded: '上传来源', liked: '本人收藏', downloaded: '本人下载' }
  if (activity.value) values.push({ key: 'activity', label: `活动：${activityNames[activity.value]}` })
  if (dates.value?.length) values.push({ key: 'dates', label: `创建日期：${dates.value.join(' 至 ')}` })
  if (includeDescendants.value) values.push({ key: 'includeDescendants', label: '包含子目录素材' })
  return values
})
function restoreView(value: LibraryViewSettings) {
  layout.value = value.layout; cardSize.value = value.cardSize; splitByDate.value = value.splitByDate
  fileType.value = value.fileType || ''
  dates.value = value.dates ? [...value.dates] : null
  includeDescendants.value = value.includeDescendants ?? false
  activity.value = value.activity || ''; filter()
  emit('restoreFolders', value)
}
const {
  active: actionsActive,
  editing,
  form,
  draft,
  pending,
  renameLocked,
  actionsLocked,
  lifecycleUncertain,
  lifecycleLabel,
  retryLifecycle,
  renameUncertain,
  cancelEdit,
  error: actionError,
  trashOpen,
  trashLoading,
  recycled,
  total: trashTotal,
  page: trashPage,
  edit,
  save,
  lifecycle,
  refreshTrash,
} = useAssetActions(props.projectId, () => {
  closePreview()
  void refresh()
}, () => props.visible !== false)
const deletable = computed(() => rows.value.some(entry => entry.asset.allowedActions?.includes('asset:remove')))
const selection = useContentSelection(() => rows.value.map(entry => entry.asset), () => actionsLocked.value || loading.value || batchBusy.value)
const batchDelete = useAssetBatchDelete(() => rows.value.map(entry => entry.asset), () => props.visible !== false && deletable.value && !actionsLocked.value && !loading.value && !trashOpen.value && !editing.value && !selected.value && !batchDownload.pending.value && !mover.value?.locked, refresh, selection.selected)
const batchDownload = useAssetBatchDownload(() => rows.value.map(entry => entry.asset), selection.selected, () => props.visible !== false && props.canDownload && !actionsLocked.value && !loading.value && !trashOpen.value && !editing.value && !selected.value && !batchDelete.pending.value && !mover.value?.locked)
const videoCards = new Map<string, InstanceType<typeof AssetHoverVideo>>()
watch(() => selection.selected.value.length, count => emit('selectionChange', count), { immediate: true })
watch(() => props.folderId, () => { selection.selected.value = [] })
const statusMoreOpen = ref(false), statusOptionsOpen = ref(false)
watch(statusMoreOpen, open => { if (!open) statusOptionsOpen.value = false })
const batchStatus = useAssetBatchStatus(() => rows.value.map(entry => entry.asset), () => props.visible !== false && !actionsLocked.value && !loading.value && !batchDelete.pending.value && !batchDownload.pending.value && !mover.value?.locked && !copier.value?.locked, refresh, selection.selected)
const canChangeStatus = computed(() => rows.value.some(entry => selection.selected.value.includes(entry.asset.id) && entry.asset.allowedActions?.includes('content:review')))
const firstSelected = computed(() => rows.value.find(entry => selection.selected.value.includes(entry.asset.id))?.asset)
watch(() => selection.selected.value.length, count => { if (!count) { statusMoreOpen.value = false; statusOptionsOpen.value = false } })
const batchBusy = computed(() => batchStatus.pending.value || batchDelete.pending.value || batchDownload.pending.value || Boolean(mover.value?.locked) || Boolean(copier.value?.locked))
const moveMessage = ref('')
function moved(ids: string[], summary: string) {
  const assets = new Set(rows.value.filter(entry => ids.includes(entry.id)).map(entry => entry.asset.id))
  selection.selected.value = selection.selected.value.filter(id => !assets.has(id))
  moveMessage.value = summary
  void refresh()
}
const deleteCount = computed(() => new Set(rows.value.filter(entry => selection.selected.value.includes(entry.asset.id) && entry.asset.allowedActions?.includes('asset:remove')).map(entry => entry.asset.id)).size)
const batchRestore = useAssetBatchRestore(() => recycled.value, () => props.visible !== false && trashOpen.value && !actionsLocked.value && !trashLoading.value, async () => {
  await refreshTrash()
  await refresh()
})
const { items, running, enqueue, pause, pauseItem, retry, clearFinished } = useAssetUploads(
  props.projectId,
  () => {
    void refresh()
  },
)
const input = ref<HTMLInputElement>()
const versionInput = ref<HTMLInputElement>(), versionTarget = ref<Asset | null>(null)
function chooseVersionTarget(asset: Asset) {
  if (!props.canUpload || !asset.allowedActions?.includes('asset:edit')) return
  versionTarget.value = { ...asset }; versionInput.value?.click()
}
function chooseVersion(event: Event) {
  const control = event.target as HTMLInputElement, file = control.files?.[0], asset = versionTarget.value
  if (file && asset && props.canUpload && asset.allowedActions?.includes('asset:edit')) enqueue([file], props.folderId, asset)
  control.value = ''; versionTarget.value = null
}
const uploadsOpen = ref(false)
watch(() => items.length, (count, previous) => { if (count > previous) uploadsOpen.value = true })
function choose(event: Event) {
  const target = event.target as HTMLInputElement
  if (props.canUpload) enqueue(Array.from(target.files || []), props.folderId)
  target.value = ''
}
function size(bytes: number | string) {
  return `${(Number(bytes) / 1024 / 1024).toFixed(1)} MB`
}
watch(
  () => props.refreshKey,
  () => {
    void refresh()
  },
)
watch(
  () => props.canUpload,
  (allowed) => {
    if (!allowed) pause()
  },
)
</script>
<template>
  <section class="asset-library" :class="{ 'asset-workspace': compact }" aria-label="项目素材">
    <DirectoryMoveDialog ref="mover" :visible="visible !== false" :project-id="projectId" :can-create-folder="canMove" :allowed="canMove && !batchDelete.pending.value && !batchDownload.pending.value" @changed="moved" />
    <DirectoryMoveDialog ref="copier" operation="copy" :visible="visible !== false" :project-id="projectId" :can-create-folder="canMove" :allowed="Boolean(canCopy) && !batchDelete.pending.value && !batchDownload.pending.value && !mover?.locked" @changed="(_, summary) => { moveMessage = summary; refresh() }" />
    <ElementEditor v-if="elementSource" :initial-asset="elementSource" :element-id="null" :project-id="projectId" :actions="projectActions || []" :visible="visible !== false" @close="elementSource = null" @saved="elementSource = null; moveMessage = '元素已创建，可在项目元素中查看'" />
    <header class="asset-toolbar asset-workspace-toolbar" :inert="batchBusy">
      <div class="asset-workspace-path"><slot name="breadcrumb"><h3>素材 <small class="muted">{{ total }}</small></h3></slot></div>
      <ElPopover placement="bottom-end" trigger="click" :width="420" popper-class="asset-controls-popover">
        <template #reference><Button variant="outline" aria-label="筛选素材"><IconFilter :size="16" />筛选<span v-if="activeFilters.length" class="asset-filter-count">{{ activeFilters.length }}</span></Button></template>
        <h4>筛选素材</h4>
    <div class="asset-filters" :inert="batchBusy">
      <ElCheckbox v-model="includeDescendants" @change="filter">包含子目录素材</ElCheckbox>
      <span class="muted">创建日期（上海时间，包含结束日）</span>
      <ElDatePicker v-model="dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="创建开始日期" end-placeholder="创建结束日期" aria-label="素材创建日期（上海时间，包含结束日）" @change="filter" />
      <ElSelect v-model="activity" placeholder="全部活动" aria-label="素材活动" @change="filter">
        <ElOption label="全部活动" value="" /><ElOption label="生成来源" value="generated" /><ElOption label="上传来源" value="uploaded" /><ElOption label="本人收藏" value="liked" /><ElOption label="本人获准下载" value="downloaded" />
      </ElSelect>
      <ElInput
        v-model="search"
        :placeholder="includeDescendants ? '搜索当前目录及子目录素材' : '搜索当前目录素材'"
        clearable
        maxlength="200"
        aria-label="素材名称"
        @keyup.enter="filter"
        @clear="filter"
      />
      <ElSelect v-model="fileType" placeholder="全部类型" aria-label="素材类型" @change="filter"
        ><ElOption label="全部类型" value="" /><ElOption label="图片" value="image" /><ElOption
          label="视频"
          value="video"
      /><ElOption v-for="(_, kind) in documentFormats" :key="kind" :label="kind.toUpperCase()" :value="kind" /></ElSelect>
      <Button variant="ghost" @click="filter">搜索</Button>
    </div>
    <div v-if="activeFilters.length" class="asset-toolbar" aria-label="当前素材筛选" :inert="batchBusy">
      <span class="muted">{{ activeFilters.length }} 项条件</span>
      <Button v-for="condition in activeFilters" :key="condition.key" variant="outline" :aria-label="`移除筛选 ${condition.label}`" @click="clearFilter(condition.key)">{{ condition.label }} ×</Button>
      <Button variant="ghost" @click="clearFilter()">清除全部筛选</Button>
    </div>

      </ElPopover>
      <ElPopover placement="bottom-end" trigger="click" :width="320" popper-class="asset-controls-popover">
        <template #reference><Button variant="outline" aria-label="素材视图"><IconLayoutGrid :size="16" />视图</Button></template>
        <h4>视图</h4><div class="asset-view-controls">
      <ElSelect v-model="layout" aria-label="素材布局"><ElOption :label="compact ? '等高画廊' : '方形网格'" value="square" /><ElOption label="瀑布流" value="masonry" /></ElSelect>
      <ElCheckbox v-model="splitByDate">按日期分组</ElCheckbox>
      <label class="muted">卡片尺寸 <ElInputNumber v-model="cardSize" :min="1" :max="8" :precision="0" aria-label="素材卡片尺寸" /></label>
        </div>
        <div :inert="batchBusy"><LibraryViewPreference :key="projectId" :project-id="projectId" :settings="viewSettings" @restore="restoreView" /></div>
      </ElPopover>
      <ElPopover placement="bottom-end" trigger="click" :width="180" popper-class="asset-controls-popover">
        <template #reference><Button variant="outline" aria-label="素材更多操作"><IconDots :size="16" /></Button></template>
        <div class="asset-more-controls"><Button variant="ghost" :disabled="loading" @click="refresh"><IconRefresh :size="16" />刷新素材</Button><Button variant="ghost" @click="trashOpen = true">素材回收站</Button><Button variant="ghost" @click="selection.selectAll(true)">选择当前页素材</Button></div>
      </ElPopover>
      <button v-if="items.length" type="button" class="folder-text-button" @click="uploadsOpen = !uploadsOpen">上传记录（{{ items.length }}）</button>
      <Button v-if="canUpload" variant="outline" @click="input?.click()"><IconUpload :size="16" />上传素材</Button>
      <input
        ref="input"
        class="asset-file-input"
        type="file"
        multiple
        :accept="assetAccept"
        aria-label="选择上传素材"
        @change="choose"
      />
      <input ref="versionInput" class="asset-file-input" type="file" :accept="assetAccept" aria-label="选择素材新版本" @change="chooseVersion" />
    </header>
    <AssetUploadPanel v-if="items.length" v-model:open="uploadsOpen" :items="items" :running="running" :can-upload="canUpload" @pause="pause" @pause-item="pauseItem" @retry="retry" @clear="clearFinished" />

    <div v-if="selection.selected.value.length || batchBusy" class="asset-toolbar asset-selection-toolbar" :class="{ 'asset-selection-dock': compact }">
      <span class="asset-selection-count"><span v-if="firstSelected" class="asset-selection-thumbnail"><ReferenceThumbnail :version-id="firstSelected.currentVersionId" :alt="firstSelected.name" fill passive /></span><strong>已选 {{ selection.selected.value.length }} 项</strong></span>
      <Button variant="ghost" :disabled="!canDownload || loading || actionsLocked || batchBusy" :title="canDownload ? '下载所选' : '暂无下载权限'" @click="batchDownload.download"><IconDownload :size="18" />下载</Button>
      <Button variant="ghost" :disabled="!canMove || loading || actionsLocked || batchBusy" @click="mover?.openMany(rows.filter(entry => selection.selected.value.includes(entry.asset.id)))"><IconFolderSymlink :size="18" />移动到</Button>
      <Button variant="ghost" :disabled="!canCopy || loading || actionsLocked || batchBusy" @click="copier?.openMany(rows.filter(entry => selection.selected.value.includes(entry.asset.id)))"><IconFolderPlus :size="18" />复制到</Button>
      <Button variant="ghost" class="asset-selection-icon" aria-label="删除所选" :title="deleteCount ? '删除所选' : '暂无删除权限'" :disabled="loading || actionsLocked || batchBusy || !deleteCount" @click="batchDelete.execute"><IconTrash :size="18" /></Button>
      <ElPopover v-model:visible="statusMoreOpen" placement="top-end" trigger="click" :width="220" popper-class="asset-controls-popover asset-batch-more">
        <template #reference><Button variant="ghost" class="asset-selection-icon" aria-label="更多批量操作" :disabled="batchBusy"><IconDots :size="18" /></Button></template>
        <ElPopover v-model:visible="statusOptionsOpen" placement="right-end" trigger="click" :width="210" popper-class="asset-controls-popover asset-batch-status">
          <template #reference><button class="asset-menu-item" :disabled="batchBusy" :title="canChangeStatus ? '设置所选素材状态' : '暂无素材审核权限'"><IconCircleDotted :size="18" />状态<IconChevronRight :size="16" class="status-menu-arrow" /></button></template>
          <header><span>状态</span><button :disabled="batchBusy || !canChangeStatus" @click="batchStatus.change('none'); statusMoreOpen = false; statusOptionsOpen = false">清除</button></header>
          <button v-for="option in assetStatuses" :key="option.value" class="asset-menu-item" :disabled="batchBusy || !canChangeStatus" @click="batchStatus.change(option.value); statusMoreOpen = false; statusOptionsOpen = false"><span class="asset-status-dot" :style="{ background: option.color }" />{{ option.label }}</button>
        </ElPopover>
      </ElPopover>
      <Button variant="ghost" class="asset-selection-close" aria-label="取消选择" :disabled="batchBusy" @click="selection.selectAll(false)"><IconX :size="20" /></Button>
      <Button v-if="batchDownload.pending.value" variant="ghost" @click="batchDownload.stop">停止下载</Button>
    </div>
    <p v-if="batchDownload.pending.value" role="status">正在读取 {{ batchDownload.currentName.value }} · {{ size(batchDownload.loadedBytes.value) }}</p>
    <p v-if="moveMessage" role="status">{{ moveMessage }}</p>
    <p v-if="batchStatus.message.value" role="status">{{ batchStatus.message.value }}</p>
    <p v-if="batchDelete.message.value" role="status">{{ batchDelete.message.value }}</p>
    <p v-if="batchDownload.message.value" role="status">{{ batchDownload.message.value }}</p>
    <p v-if="splitByDate" class="muted">按上海日期分组，仅展示当前页素材。</p>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="muted" role="status">正在加载素材…</p>
    <div v-else :style="{ '--asset-card-width': `${contentCardWidth(cardSize)}px`, '--asset-row-height': `${contentCardWidth(cardSize) + 60}px` }">
    <section v-for="dateGroup in dateGroups" :key="dateGroup.key" class="asset-date-group">
      <h4 v-if="splitByDate">{{ dateGroup.label }} · {{ dateGroup.rows.length }} 项</h4>
      <div :class="layout === 'masonry' ? 'asset-masonry' : compact ? 'asset-filmstrip' : 'asset-grid'">
      <article v-for="entry in dateGroup.rows" :key="entry.id" class="asset-card" :class="{ 'is-selected': selection.selected.value.includes(entry.asset.id) }" @mouseenter="videoCards.get(entry.id)?.start()" @mouseleave="videoCards.get(entry.id)?.stop()" :inert="batchBusy" :style="compact && layout === 'square' ? { '--media-ratio': entry.asset.file.width && entry.asset.file.height ? entry.asset.file.width / entry.asset.file.height : 0.8 } : undefined">
        <ElCheckbox :model-value="selection.selected.value.includes(entry.asset.id)" :aria-label="`选择素材 ${entry.name}`" :disabled="actionsLocked || batchBusy" @change="selection.toggle(entry.asset.id, Boolean($event))" />
        <button
          class="asset-preview-button"
          :style="layout === 'masonry' && (entry.asset.file.width || 0) > 0 && (entry.asset.file.height || 0) > 0 ? { aspectRatio: `${entry.asset.file.width} / ${entry.asset.file.height}` } : undefined"
          :aria-label="'预览 ' + entry.name"
          @click="openMedia(entry.asset)"
        >
          <AssetHoverVideo v-if="entry.asset.mediaType === 'video'" :ref="el => { if (el) videoCards.set(entry.id, el as InstanceType<typeof AssetHoverVideo>); else videoCards.delete(entry.id) }" :version-id="entry.asset.currentVersionId" :name="entry.name" :enabled="visible !== false && !selected && !selection.selected.value.length" />
          <ReferenceThumbnail v-else-if="entry.asset.mediaType === 'image'" :version-id="entry.asset.currentVersionId" :alt="entry.name" :allow-original="entry.asset.mediaType === 'image' && Number(entry.asset.file.byteSize) <= 20 * 1024 * 1024" fill passive />
          <template v-else><IconFileText :size="44" /><span>{{ entry.name.split('.').pop()?.toUpperCase() }}</span></template>
          <span v-if="lastViewedId === entry.asset.id && !selected" class="asset-last-viewed"><IconEye :size="14" />最近查看</span>
        </button>
        <span class="asset-hover-status" :class="{ 'has-status': assetStatus(entry.asset.workStatus) }" :title="assetStatus(entry.asset.workStatus)?.label || '无状态'">
          <span v-if="assetStatus(entry.asset.workStatus)" class="asset-status-dot" :style="{ background: assetStatus(entry.asset.workStatus)?.color }" /><IconCircleDotted v-else :size="13" />
          <span class="asset-status-label">{{ assetStatus(entry.asset.workStatus)?.label || '无状态' }}</span>
        </span>
        <div class="asset-hover-shortcuts">
          <button type="button" class="asset-round-action" aria-label="下载素材" :disabled="!canDownload || mediaLoading" :title="canDownload ? '下载' : '暂无下载权限'" @click="canDownload && openMedia(entry.asset, true)"><IconDownload :size="19" /></button>
        </div>
        <span v-if="entry.asset.uploaded" class="asset-upload-origin" title="上传来源" aria-label="上传来源"><IconCloud :size="15" /></span>
        <strong class="asset-name" :title="entry.name">{{ entry.name }}</strong>
        <AssetCardMenu :compact="compact" :name="entry.name">
          <button class="asset-menu-item" @click="openMedia(entry.asset)"><IconMaximize :size="18" />打开</button>
          <button class="asset-menu-item" @click="selection.toggle(entry.asset.id, !selection.selected.value.includes(entry.asset.id))"><IconCheckbox :size="18" />{{ selection.selected.value.includes(entry.asset.id) ? '取消选择' : '选择' }}</button>
          <button class="asset-menu-item" :disabled="!canCreateElement || entry.asset.mediaType !== 'image'" :title="entry.asset.mediaType !== 'image' ? '元素目前支持图片素材' : !canCreateElement ? '暂无创建元素权限' : '从当前图片创建元素'" @click="elementSource = entry.asset"><IconAt :size="18" />创建元素</button>
          <span class="asset-menu-divider" />
          <button class="asset-menu-item" :disabled="actionsLocked || !entry.asset.allowedActions?.includes('asset:edit')" :title="!entry.asset.allowedActions?.includes('asset:edit') ? '暂无重命名权限' : ''" @click="edit(entry.asset)"><IconPencil :size="18" />重命名</button>
          <button class="asset-menu-item" :disabled="!canDownload || mediaLoading" :title="canDownload ? '' : '暂无下载权限'" @click="canDownload && openMedia(entry.asset, true)"><IconDownload :size="18" />下载</button>
          <button class="asset-menu-item" :disabled="!canMove" :title="canMove ? '' : '暂无移动权限'" @click="mover?.open(entry)"><IconFolderSymlink :size="18" />移动到</button>
          <button class="asset-menu-item" :disabled="!canCopy" :title="canCopy ? '' : '需要目录写入、素材创建及引用权限'" @click="copier?.open(entry)"><IconFolderPlus :size="18" />复制到</button>
          <span class="asset-menu-divider" />
          <button class="asset-menu-item asset-menu-danger" :disabled="actionsLocked || !entry.asset.allowedActions?.includes('asset:remove')" :title="!entry.asset.allowedActions?.includes('asset:remove') ? '暂无删除权限' : '移入回收站'" @click="lifecycle(entry.asset, false)"><IconTrash :size="18" />删除</button>
        </AssetCardMenu>
      </article>
      </div>
    </section>
    </div>
    <section v-if="!loading && !error && !rows.length" class="asset-empty" aria-label="素材列表为空">
      <span class="asset-empty-icon"><IconSearch :size="28" aria-hidden="true" /></span>
      <template v-if="activeFilters.length">
        <h4>没有符合筛选条件的素材</h4>
        <p class="muted">调整类型、日期或名称，或清除筛选后查看当前目录。</p>
        <Button variant="outline" :disabled="actionsLocked || batchBusy" @click="clearFilter()">清除筛选</Button>
      </template>
      <template v-else>
        <h4>当前目录还没有素材</h4>
        <p v-if="canUpload && canGenerate" class="muted">上传已有素材，或进入创作区生成图片和视频。</p>
        <p v-else-if="canUpload" class="muted">上传已有素材，整理到当前目录。</p>
        <p v-else-if="canGenerate" class="muted">进入创作区生成图片和视频，开始积累项目素材。</p>
        <p v-else class="muted">项目成员添加素材后，你可以在这里查看获准访问的内容。</p>
        <div class="asset-empty-actions">
          <Button v-if="canUpload" variant="outline" :disabled="actionsLocked || batchBusy" @click="input?.click()"><IconUpload :size="16" />上传素材</Button>
          <Button v-if="canGenerate" :disabled="actionsLocked || batchBusy" @click="emit('create')">开始创作</Button>
        </div>
      </template>
    </section>
    <p v-if="actionError" class="project-error" role="alert">{{ actionError }}</p>
    <div v-if="lifecycleUncertain" role="status">{{ lifecycleLabel }}结果尚未确认。<Button :disabled="pending" @click="retryLifecycle">重试确认原请求</Button></div>
    <ElDialog
      :model-value="actionsActive && Boolean(editing)"
      title="重命名素材"
      width="min(460px, 94vw)"
      :close-on-click-modal="false"
      :show-close="!actionsLocked && !batchRestore.pending.value"
      :close-on-press-escape="!actionsLocked && !batchRestore.pending.value"
      :before-close="cancelEdit"
    >
      <template #header="{ titleId, titleClass }">
        <DialogHeading :title-id="titleId" :title-class="titleClass" title="重命名素材" />
      </template>
      <ElForm ref="form" :model="draft" label-position="top" :disabled="renameLocked"
        ><ElFormItem
          label="素材名称"
          prop="name"
          :rules="[
            { required: true, whitespace: true, message: '请输入素材名称', trigger: 'blur' },
          ]"
          ><ElInput v-model="draft.name" maxlength="200" /></ElFormItem
      ></ElForm>
      <p v-if="renameUncertain" role="status">重命名结果尚未确认，请重试原请求；确认前暂不能修改或关闭。</p>
      <p v-if="actionError" class="project-error" role="alert">{{ actionError }}</p>
    <div v-if="lifecycleUncertain" role="status">{{ lifecycleLabel }}结果尚未确认。<Button :disabled="pending" @click="retryLifecycle">重试确认原请求</Button></div>
      <template #footer
        ><Button variant="ghost" :disabled="renameLocked" @click="cancelEdit">取消</Button
        ><Button :disabled="pending || lifecycleUncertain" @click="save">{{ renameUncertain ? '重试确认原请求' : '保存' }}</Button></template
      >
    </ElDialog>
    <ElDialog
      :model-value="actionsActive && trashOpen"
      @update:model-value="actionsActive && (trashOpen = $event)"
      title="素材回收站"
      width="min(760px, 94vw)"
      :close-on-click-modal="false"
      :show-close="!actionsLocked && !batchRestore.pending.value"
      :close-on-press-escape="!actionsLocked && !batchRestore.pending.value"
    >
      <template #header="{ titleId, titleClass }">
        <DialogHeading :title-id="titleId" :title-class="titleClass" title="素材回收站" />
      </template>
      <p v-if="actionError" class="project-error" role="alert">{{ actionError }}</p>
    <div v-if="lifecycleUncertain" role="status">{{ lifecycleLabel }}结果尚未确认。<Button :disabled="pending" @click="retryLifecycle">重试确认原请求</Button></div>
      <p v-if="trashLoading" role="status">正在加载…</p>
      <div class="asset-toolbar">
        <ElCheckbox :model-value="batchRestore.allSelected.value" :disabled="actionsLocked || trashLoading || batchRestore.pending.value" @change="batchRestore.selectAll(Boolean($event))">选择当前页可恢复素材</ElCheckbox>
        <Button :disabled="actionsLocked || trashLoading || batchRestore.pending.value || !batchRestore.selected.value.length" @click="batchRestore.restore">{{ batchRestore.pending.value ? '正在恢复…' : `恢复所选（${batchRestore.selected.value.length}）` }}</Button>
      </div>
      <p v-if="batchRestore.message.value" role="status">{{ batchRestore.message.value }}</p>
      <template v-if="!trashLoading"
        ><div v-for="item in recycled" :key="item.id" class="asset-toolbar">
          <ElCheckbox :model-value="batchRestore.selected.value.includes(item.id)" :aria-label="`选择恢复 ${item.name}`" :disabled="actionsLocked || batchRestore.pending.value || !item.canRestore" @change="batchRestore.toggle(item.id, Boolean($event))" />
          <span>{{ item.name }} · 恢复期限 {{ formatProjectDate(item.restoreUntil) }}</span
          ><Button
            variant="ghost"
            :disabled="actionsLocked || batchRestore.pending.value || !item.canRestore"
            @click="lifecycle(item, true)"
            >恢复</Button
          >
        </div>
        <p v-if="!recycled.length && !actionError" class="muted">
          没有可查看的回收素材。
        </p></template
      >
      <ElPagination
        v-if="trashTotal > 30"
        v-model:current-page="trashPage"
        :disabled="batchRestore.pending.value"
        :page-size="30"
        :total="trashTotal"
        layout="prev, pager, next"
      />
    </ElDialog>
    <ElPagination
      v-if="total > 30"
      v-model:current-page="page"
      :disabled="batchBusy"
      :page-size="30"
      :total="total"
      layout="prev, pager, next"
    />
    <ElDialog
      :model-value="visible !== false && Boolean(selected)"
      :title="selected?.name"
      width="min(960px, 94vw)"
      :before-close="closeMediaPreview"
    >
      <template #header="{ titleId, titleClass }">
        <DialogHeading :title-id="titleId" :title-class="titleClass" :title="selected?.name || '素材预览'" />
      </template>
      <p v-if="mediaLoading" role="status">
        正在授权读取 {{ size(loadedBytes) }} /
        {{ size(selected?.file.byteSize || 0) }}，大文件需要等待完整下载。
      </p>
      <p v-if="mediaError" class="project-error" role="alert">{{ mediaError }}</p>
      <img
        v-if="mediaUrl && selected?.mediaType === 'image'"
        class="asset-media"
        :src="mediaUrl"
        :alt="selected.name"
      />
      <video
        v-if="mediaUrl && selected?.mediaType === 'video'"
        class="asset-media"
        :src="mediaUrl"
        controls
        preload="metadata"
      />
      <AssetPdfPreview v-if="pdfBlob" :source="pdfBlob" />
      <section v-if="documentSections.length" class="asset-document-text" aria-label="文档文本预览">
        <p class="muted">文本预览不保留原件排版；HTML显示源码。</p>
        <article v-for="(section, index) in documentSections" :key="index">
          <h4 v-if="documentSections.length > 1">第 {{ index + 1 }} 页</h4>
          <pre>{{ section || '此页没有可提取的文本' }}</pre>
        </article>
      </section>
      <MediaComments
        :visible="visible !== false"
        ref="comments"
        v-if="selected"
        :key="selected.currentVersionId"
        :target="{ assetVersionId: selected.currentVersionId }"
        :media-kind="selected.mediaType"
      />
    </ElDialog>
  </section>
</template>



