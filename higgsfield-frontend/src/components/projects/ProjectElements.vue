<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import StudioSelect from '@/components/ui/StudioSelect.vue'
import StudioPopover from '@/components/ui/StudioPopover.vue'
import StudioPagination from '@/components/ui/StudioPagination.vue'
import { ref, watch, computed, useId } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElCheckbox, ElMessageBox } from 'element-plus'
import { IconRefresh, IconAdjustmentsHorizontal, IconPlus, IconSearch, IconFilter, IconLayoutGrid, IconUpload, IconFolder, IconAt } from '@tabler/icons-vue'
import DirectoryMoveDialog from './DirectoryMoveDialog.vue'
import ElementBatchCopyDialog from './ElementBatchCopyDialog.vue'
import type { ElementRecord } from '@/api/elements'
import { useElementDownload } from '@/composables/useElementDownload'
import { useContentSelection } from '@/composables/useContentSelection'
import ElementViewCollection from './ElementViewCollection.vue'
import ElementViewPreference from './ElementViewPreference.vue'
import type { ElementViewSettings } from '@/api/viewPreferences'
import Button from '@/components/ui/Button.vue'
import ElementEditor from './ElementEditor.vue'
import ElementImportDialog from './ElementImportDialog.vue'
import PropertyDefinitionsDialog from './PropertyDefinitionsDialog.vue'
import { useElementLibrary } from '@/composables/useElementLibrary'
import { useElements } from '@/composables/useElements'
import { useElementBatchDelete } from '@/composables/useElementBatchDelete'
import '@/styles/elements.css'
const props = defineProps<{
  projectId: string
  visible?: boolean
  actions: string[]
  using?: boolean
  useError?: string
}>()
const emit = defineEmits<{ use: [elements: ElementRecord[], completed?: () => void] }>()
const mover = ref<InstanceType<typeof DirectoryMoveDialog>>()
const copier = ref<InstanceType<typeof ElementBatchCopyDialog>>()
const moveMessage = ref('')
const propertiesOpen = ref(false)
const importOpen = ref(false)
const layout = ref<'grid' | 'board' | 'table'>('table')
const cardSize = ref(4),
  splitByDate = ref(false)
const route = useRoute()
const router = useRouter()
function previewAsset(versionId: string) {
  if (batchBusy.value) return
  void router.push({ query: { ...route.query, tab: 'folders', asset: undefined, assetVersion: versionId, previewFrom: 'elements' } })
}
const {
  rows,
  total,
  page,
  search,
  category,
  group,
  folderId,
  workStatus,
  trash,
  loading,
  error,
  pending,
  editorOpen,
  editingId,
  refresh,
  filter,
  open,
} = useElements(props.projectId, () => props.visible !== false)
const categoryPanelId = useId()
const toolbarMenu = ref('')
const searchInputId = useId()
const statusInputId = useId()
const dateSwitchId = useId()
function applySearch() { filter(); toolbarMenu.value = '' }
function clearSearch() { search.value = ''; filter() }
watch(() => props.visible, value => { if (value === false) toolbarMenu.value = '' })
const library = useElementLibrary(props.projectId, rows, () => props.visible !== false && !trash.value, () => ({ q: search.value, category: category.value || undefined, statusGroup: group.value || undefined, workStatus: workStatus.value || undefined, folderId: folderId.value || undefined }))
function chooseGroup(value: '' | 'active' | 'drafts') { group.value = value; folderId.value = ''; filter() }
async function addFolder() {
  try {
    const { value } = await ElMessageBox.prompt('输入元素文件夹名称', '添加文件夹', { inputPattern: /\S+/, inputErrorMessage: '请输入名称', confirmButtonText: '创建', cancelButtonText: '取消' })
    await library.addFolder(value.trim())
  } catch { /* 取消时保留当前列表 */ }
}
const selection = useContentSelection(
  () => rows.value,
  () => pending.value || loading.value || batchBusy.value,
)
const batchDelete = useElementBatchDelete(
  () => rows.value,
  () =>
    props.visible !== false &&
    !trash.value &&
    props.actions.includes('element:remove') &&
    !pending.value &&
    !loading.value &&
    !editorOpen.value &&
    !mover.value?.locked &&
    !copier.value?.locked &&
    !downloader.pending.value,
  refresh,
  selection.selected,
)
const downloader = useElementDownload(
  () =>
    props.visible !== false &&
    props.actions.includes('asset:download') &&
    !trash.value &&
    !pending.value &&
    !loading.value &&
    !editorOpen.value &&
    !batchDelete.pending.value &&
    !copier.value?.locked &&
    !mover.value?.locked,
  (ids) => {
    selection.selected.value = selection.selected.value.filter((id) => !ids.includes(id))
  },
)
const batchBusy = computed(
  () =>
    batchDelete.pending.value ||
    Boolean(mover.value?.locked) ||
    Boolean(copier.value?.locked) ||
    downloader.pending.value,
)
const copyable = computed(() =>
  rows.value.filter(
    (item) =>
      selection.selected.value.includes(item.id) &&
      (!item.allowedActions || item.allowedActions.includes('element:copy')),
  ),
)
function copied(ids: string[]) {
  selection.selected.value = selection.selected.value.filter((id) => !ids.includes(id))
  void refresh()
}
const movable = computed(() =>
  rows.value.filter(
    (item) =>
      selection.selected.value.includes(item.id) &&
      (!item.allowedActions || item.allowedActions.includes('element:edit')),
  ),
)
const deleteCount = computed(
  () =>
    rows.value.filter(
      (item) =>
        selection.selected.value.includes(item.id) &&
        (!item.allowedActions || item.allowedActions.includes('element:remove')),
    ).length,
)
function moved(ids: string[], summary: string) {
  selection.selected.value = selection.selected.value.filter((id) => !ids.includes(id))
  moveMessage.value = summary
  void refresh()
}
const viewSettings = computed<ElementViewSettings>(() => ({
  layout: layout.value,
  cardSize: cardSize.value,
  splitByDate: splitByDate.value,
  category: category.value || null,
  workStatus: workStatus.value || null,
  statusGroup: group.value || null,
}))
function restoreView(value: ElementViewSettings) {
  layout.value = value.layout
  category.value = value.category || ''
  workStatus.value = value.workStatus || ''
  cardSize.value = value.cardSize
  splitByDate.value = value.splitByDate
  group.value = value.statusGroup || ''
  filter()
}
const categoryNames = { character: '角色', scene: '场景', prop: '道具', other: '其他' }
watch(
  () => [route.params.id, route.query.element],
  () => {
    const id = route.query.element
    if (
      route.params.id === props.projectId &&
      typeof id === 'string' &&
      /^[1-9]\d*$/.test(id) &&
      !editorOpen.value &&
      !batchBusy.value
    )
      open(id)
  },
  { immediate: true },
)
function saved() {
  editorOpen.value = false
  void refresh()
}
</script>
<template>
  <section class="element-workspace element-library">
    <header class="element-library-heading" :inert="batchBusy">
      <strong>{{ trash ? '元素回收站' : '全部元素' }}</strong>
      <div class="element-library-actions">
        <Button v-if="!trash && actions.includes('element:import')" variant="outline" @click="importOpen = true"><IconUpload :size="16" />导入</Button>
        <Button v-if="!trash" variant="outline" :disabled="library.exporting.value" @click="library.exportCsv">{{ library.exporting.value ? '导出中…' : '导出 CSV' }}</Button>
        <Button v-if="!trash && actions.includes('element:create')" @click="open(null)"><IconPlus :size="17" />新建元素</Button>
        <Button v-if="trash" variant="ghost" @click="trash = false">返回元素</Button>
      </div>
    </header>
    <div v-if="!trash" class="element-library-navigation" :inert="batchBusy">
      <Tabs :model-value="category || 'all'" @update:model-value="value => { category = value === 'all' ? '' : value as typeof category; filter() }">
        <TabsList class="element-category-tabs studio-tabs studio-pill-tabs" aria-label="元素分类">
          <TabsTrigger :aria-controls="categoryPanelId" value="all">全部</TabsTrigger>
          <TabsTrigger :aria-controls="categoryPanelId" v-for="(label, value) in categoryNames" :key="value" :value="value">{{ label }}</TabsTrigger>
        </TabsList>
      </Tabs>
      <div class="element-library-actions">
        <StudioPopover :disabled="visible === false" :visible="toolbarMenu === 'search'" placement="bottom-end" :width="300" popper-class="element-toolbar-popover" @update:visible="toolbarMenu = $event ? 'search' : ''">
          <template #reference><Button variant="ghost" class="element-toolbar-button" :class="{ 'has-value': search }"><IconSearch :size="16" />搜索<span v-if="search" class="toolbar-value-dot" aria-label="已设置搜索条件"></span></Button></template>
          <form class="element-library-options" @submit.prevent="applySearch">
            <label :for="searchInputId">搜索元素</label>
            <Input :id="searchInputId" v-model="search" placeholder="输入名称或别名" aria-label="搜索名称或别名" />
            <div class="element-search-actions"><Button type="button" variant="ghost" :disabled="!search" @click="clearSearch">清除</Button><Button type="submit">搜索</Button></div>
          </form>
        </StudioPopover>
        <StudioPopover :disabled="visible === false" :visible="toolbarMenu === 'filter'" placement="bottom-end" :width="260" popper-class="element-toolbar-popover" @update:visible="toolbarMenu = $event ? 'filter' : ''">
          <template #reference><Button variant="ghost" class="element-toolbar-button" :class="{ 'has-value': workStatus }"><IconFilter :size="16" />筛选<span v-if="workStatus" class="toolbar-value-dot" aria-label="已设置筛选条件"></span></Button></template>
          <div class="element-library-options"><label :for="statusInputId">制作状态</label><StudioSelect :id="statusInputId" v-model="workStatus" aria-label="制作状态" :options="[{ label: '全部', value: '' }, { label: '未开始', value: 'none' }, { label: '制作中', value: 'working' }, { label: '待审核', value: 'review' }, { label: '已通过', value: 'approved' }, { label: '已驳回', value: 'rejected' }]" @change="filter" /><Button variant="ghost" :disabled="!workStatus" @click="workStatus = ''; filter()">重置筛选</Button></div>
        </StudioPopover>
        <StudioPopover :disabled="visible === false" :visible="toolbarMenu === 'view'" placement="bottom-end" :width="280" popper-class="element-toolbar-popover" @update:visible="toolbarMenu = $event ? 'view' : ''">
          <template #reference><Button variant="ghost" class="element-toolbar-button"><IconLayoutGrid :size="16" />视图</Button></template>
          <div class="element-library-options">
            <span class="toolbar-field-label">显示方式</span>
            <StudioSelect v-model="layout" aria-label="元素布局" :options="[{ label: '表格', value: 'table' }, { label: '网格', value: 'grid' }, { label: '看板', value: 'board' }]" />
            <div class="element-view-switch"><label :for="dateSwitchId">按日期分组</label><Switch :id="dateSwitchId" v-model="splitByDate" /></div>
            <div class="element-card-size" :class="{ 'is-disabled': layout === 'table' }"><div><span>卡片尺寸</span><span>{{ cardSize }} / 8</span></div><Slider :model-value="[cardSize]" :min="1" :max="8" :step="1" :disabled="layout === 'table'" aria-label="卡片尺寸" @update:model-value="value => { if (value?.[0] !== undefined) cardSize = value[0] }" /><small v-if="layout === 'table'">切换为网格或看板后可调整</small></div>
            <Separator />
            <ElementViewPreference compact :project-id="projectId" :settings="viewSettings" @restore="restoreView" />
            <div class="element-view-menu">
              <Button variant="ghost" @click="refresh"><IconRefresh :size="16" /><span>刷新列表</span></Button>
              <Button v-if="actions.includes('element:configure')" variant="ghost" @click="toolbarMenu = ''; propertiesOpen = true"><IconAdjustmentsHorizontal :size="16" /><span>属性配置</span></Button>
              <Separator v-if="actions.includes('element:remove')" />
            </div>
          </div>
        </StudioPopover>
      </div>
    </div>
    <p v-if="library.error.value" class="project-error" role="alert">{{ library.error.value }}</p>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载元素…</p>
    <template v-else>
      <div v-if="selection.selected.value.length" class="element-toolbar element-batch-toolbar">
        <ElCheckbox
          :model-value="selection.allSelected.value"
          :disabled="batchBusy"
          @change="selection.selectAll(Boolean($event))"
          >选择当前页元素</ElCheckbox
        >
        <Button
          v-if="actions.includes('generation:create')"
          :disabled="using || batchBusy || !selection.selected.value.length"
          @click="
            emit(
              'use',
              rows.filter((item) => selection.selected.value.includes(item.id)),
            )
          "
          >{{ using ? '正在检查引用…' : `使用所选（${selection.selected.value.length}）` }}</Button
        >
        <Button
          v-if="actions.includes('asset:download')"
          :disabled="using || batchBusy || !selection.selected.value.length"
          @click="
            downloader.download(rows.filter((item) => selection.selected.value.includes(item.id)))
          "
          >下载所选图片（{{ selection.selected.value.length }}）</Button
        ><Button v-if="downloader.pending.value" variant="ghost" @click="downloader.stop"
          >停止下载</Button
        >
        <Button
          v-if="actions.includes('element:copy')"
          :disabled="using || batchBusy || !copyable.length"
          @click="copier?.open(copyable)"
          >复制所选（{{ copyable.length }}）</Button
        >
        <Button
          v-if="actions.includes('element:edit')"
          :disabled="batchBusy || !movable.length"
          @click="mover?.openMany(movable)"
          >移动所选（{{ movable.length }}）</Button
        >
        <Button
          v-if="actions.includes('element:remove')"
          :disabled="batchBusy || !deleteCount"
          @click="batchDelete.execute"
          >{{ batchDelete.pending.value ? '正在删除…' : `删除所选（${deleteCount}）` }}</Button
        >
        <Button
          variant="ghost"
          :disabled="batchBusy || !selection.selected.value.length"
          @click="selection.selectAll(false)"
          >取消选择</Button
        >
      </div>
      <p v-if="batchDelete.message.value" role="status">{{ batchDelete.message.value }}</p>
      <p v-if="downloader.pending.value" role="status">
        正在读取 {{ downloader.currentName.value }} · {{ downloader.loadedBytes.value }} 字节
      </p>
      <p v-if="downloader.message.value" role="status">{{ downloader.message.value }}</p>
      <p v-if="moveMessage" role="status">{{ moveMessage }}</p>
      <div class="element-library-body"><div :id="categoryPanelId" class="element-library-content" role="tabpanel" aria-label="元素分类结果"><ElementViewCollection
        selectable
        :selected="selection.selected.value"
        :selection-disabled="batchBusy"
        @select="selection.toggle"
        @preview="previewAsset"
        :rows="library.displayRows.value"
        :layout="layout"
        :card-size="cardSize"
        :split-by-date="splitByDate"
        @open="!batchBusy && open($event.id)"
      /></div>
      <aside class="element-library-sidebar" aria-label="元素范围">
        <button :class="{ active: !group && !folderId }" @click="chooseGroup('')"><IconAt :size="21" />全部元素</button>
        <small>状态</small>
        <button :class="{ active: group === 'active' }" @click="chooseGroup('active')">✧ 已通过</button>
        <button :class="{ active: group === 'drafts' }" @click="chooseGroup('drafts')">▤ 草稿</button>
        <small>文件夹</small>
        <button v-for="folder in library.folders.value" :key="folder.id" :class="{ active: folderId === folder.id }" :style="{ paddingLeft: `${12 + folder.depth * 12}px` }" @click="folderId = folder.id; group = ''; filter()"><IconFolder :size="18" />{{ folder.name }}</button>
        <button v-if="actions.includes('folder:write')" :disabled="library.creating.value" @click="addFolder"><IconPlus :size="18" />添加文件夹</button>
      </aside></div>
    </template>
    <ElementBatchCopyDialog
      :visible="visible !== false"
      ref="copier"
      :allowed="
        actions.includes('element:copy') &&
        !trash &&
        !batchDelete.pending.value &&
        !editorOpen &&
        !pending &&
        !using &&
        !mover?.locked
      "
      @changed="copied"
    />
    <DirectoryMoveDialog
      :visible="visible !== false"
      ref="mover"
      :project-id="projectId"
      kind="element"
      :can-create-folder="actions.includes('folder:write')"
      :allowed="
        actions.includes('element:edit') &&
        !trash &&
        !batchDelete.pending.value &&
        !editorOpen &&
        !pending
      "
      @changed="moved"
    />
    <StudioPagination
      v-if="total > 30"
      v-model:current-page="page"
      :disabled="pending || batchBusy"
      :page-size="30"
      :total="total"
      layout="prev, pager, next"
    />
    <ElementEditor
      :visible="visible !== false"
      v-if="editorOpen"
      :project-id="projectId"
      :element-id="editingId"
      :using="using"
      :use-error="useError"
      @use="
        (item) =>
          emit('use', [item], () => {
            editorOpen = false
          })
      "
      :actions="actions"
      @close="editorOpen = false"
      @saved="saved"
    />
    <ElementImportDialog
      :visible="visible !== false"
      v-if="importOpen"
      :project-id="projectId"
      :can-import="actions.includes('element:import')"
      :can-upload="actions.includes('asset:upload')"
      :can-create="actions.includes('element:create')"
      @close="importOpen = false"
      @changed="refresh"
    />
    <PropertyDefinitionsDialog
      :visible="visible !== false"
      v-if="propertiesOpen"
      :project-id="projectId"
      @close="propertiesOpen = false"
    />
  </section>
</template>

