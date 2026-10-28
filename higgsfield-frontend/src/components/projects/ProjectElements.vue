<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElInput, ElSelect, ElOption, ElPagination, ElCheckbox, ElInputNumber } from 'element-plus'
import { IconPlus } from '@tabler/icons-vue'
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
import { useElements } from '@/composables/useElements'
import { useElementBatchDelete } from '@/composables/useElementBatchDelete'
import { useElementBatchRestore } from '@/composables/useElementBatchRestore'
import { formatProjectDate } from '@/utils/projects'
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
const layout = ref<'grid' | 'board' | 'table'>('grid')
const cardSize = ref(4),
  splitByDate = ref(false)
const route = useRoute()
const {
  rows,
  recycled,
  total,
  page,
  search,
  category,
  group,
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
  restore,
} = useElements(props.projectId, () => props.visible !== false)
const batchRestore = useElementBatchRestore(
  () => recycled.value,
  () => props.visible !== false && trash.value && props.actions.includes('element:remove') && !pending.value && !loading.value,
  refresh,
)
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
  <section class="element-workspace">
    <header class="element-toolbar" :inert="batchBusy">
      <h2>{{ trash ? '元素回收站' : '项目元素' }}</h2>
      <Button
        v-if="!trash && actions.includes('element:import')"
        variant="ghost"
        @click="importOpen = true"
        >导入元素</Button
      >
      <Button
        v-if="actions.includes('element:configure')"
        variant="ghost"
        @click="propertiesOpen = true"
        >属性配置</Button
      >
      <Button variant="ghost" :disabled="loading || batchRestore.pending.value" @click="refresh"
        >刷新</Button
      ><Button
        v-if="actions.includes('element:remove')"
        variant="ghost"
        :disabled="pending || batchRestore.pending.value"
        @click="trash = !trash"
        >{{ trash ? '返回元素' : '回收站' }}</Button
      ><Button v-if="!trash && actions.includes('element:create')" @click="open(null)"
        ><IconPlus :size="16" />新建元素</Button
      >
    </header>
    <div v-show="!trash" class="element-toolbar" :inert="batchBusy">
      <ElementViewPreference
        :key="projectId"
        :project-id="projectId"
        :settings="viewSettings"
        @restore="restoreView"
      />
      <ElCheckbox v-model="splitByDate">按日期分组</ElCheckbox>
      <label class="muted"
        >卡片尺寸
        <ElInputNumber
          v-model="cardSize"
          :min="1"
          :max="8"
          :precision="0"
          :disabled="layout === 'table'"
          aria-label="元素卡片尺寸"
      /></label>
      <ElSelect
        v-model="workStatus"
        placeholder="全部制作状态"
        aria-label="制作状态"
        @change="filter"
      >
        <ElOption label="全部制作状态" value="" /><ElOption label="未开始" value="none" /><ElOption
          label="制作中"
          value="working"
        />
        <ElOption label="待审核" value="review" /><ElOption
          label="已通过"
          value="approved"
        /><ElOption label="已驳回" value="rejected" />
      </ElSelect>
      <ElInput
        v-model="search"
        placeholder="搜索名称或别名"
        clearable
        maxlength="200"
        @keyup.enter="filter"
        @clear="filter"
      /><ElSelect v-model="category" aria-label="元素分类" @change="filter"
        ><ElOption label="全部分类" value="" /><ElOption
          v-for="(label, value) in categoryNames"
          :key="value"
          :value="value"
          :label="label" /></ElSelect
      ><ElSelect v-model="group" aria-label="元素状态" @change="filter"
        ><ElOption label="全部状态" value="" /><ElOption
          label="Active · 已通过"
          value="active" /><ElOption
          label="Drafts · 未开始/制作中/待审核"
          value="drafts" /></ElSelect
      ><Button variant="ghost" @click="filter">搜索</Button>
      <ElSelect v-model="layout" aria-label="元素布局"
        ><ElOption label="网格" value="grid" /><ElOption label="看板" value="board" /><ElOption
          label="表格"
          value="table"
      /></ElSelect>
    </div>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载元素…</p>
    <template v-else-if="trash">
      <div v-if="actions.includes('element:remove')" class="element-toolbar">
        <ElCheckbox
          :model-value="batchRestore.allSelected.value"
          :disabled="pending || batchRestore.pending.value"
          @change="batchRestore.selectAll(Boolean($event))"
          >选择当前页可恢复元素</ElCheckbox
        >
        <Button
          :disabled="pending || batchRestore.pending.value || !batchRestore.selected.value.length"
          @click="batchRestore.restore"
          >{{
            batchRestore.pending.value
              ? '正在恢复…'
              : `恢复所选（${batchRestore.selected.value.length}）`
          }}</Button
        >
      </div>
      <p v-if="batchRestore.message.value" role="status">{{ batchRestore.message.value }}</p>
      <div v-for="item in recycled" :key="item.id" class="element-picker-row">
        <ElCheckbox
          v-if="actions.includes('element:remove')"
          :model-value="batchRestore.selected.value.includes(item.id)"
          :aria-label="`选择恢复 ${item.name}`"
          :disabled="pending || batchRestore.pending.value || !item.canRestore"
          @change="batchRestore.toggle(item.id, Boolean($event))"
        />
        <span
          >{{ item.name
          }}<small class="muted">
            · 恢复期限 {{ formatProjectDate(item.restoreUntil) }}</small
          ></span
        ><Button
          variant="ghost"
          :disabled="
            pending ||
            batchRestore.pending.value ||
            !item.canRestore ||
            !actions.includes('element:remove')
          "
          @click="restore(item)"
          >{{ item.canRestore ? '恢复' : '不可恢复' }}</Button
        >
      </div>
      <p v-if="!recycled.length" class="muted">没有可查看的回收元素。</p></template
    >
    <template v-else>
      <div class="element-toolbar">
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
      <ElementViewCollection
        selectable
        :selected="selection.selected.value"
        :selection-disabled="batchBusy"
        @select="selection.toggle"
        :rows="rows"
        :layout="layout"
        :card-size="cardSize"
        :split-by-date="splitByDate"
        @open="!batchBusy && open($event.id)"
      />
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
    <ElPagination
      v-if="total > 30"
      v-model:current-page="page"
      :disabled="pending || batchRestore.pending.value || batchBusy"
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

