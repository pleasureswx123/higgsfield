<script setup lang="ts">
import type { Asset } from '@/api/assets'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { computed, ref, watch } from 'vue'
import { useFolderPresentation } from '@/composables/useFolderPresentation'
import { useFolderBatchRestore } from '@/composables/useFolderBatchRestore'
import ProjectAssets from './ProjectAssets.vue'
import '@/styles/folders.css'
import {
  ElDialog,
  ElPopover,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  ElPagination,
  ElCheckbox,
  type FormRules,
} from 'element-plus'
import { IconFolder, IconPlus, IconTrash, IconSearch } from '@tabler/icons-vue'
import { useFolders } from '@/composables/useFolders'
import { formatProjectDate } from '@/utils/projects'
import type { FolderColor } from '@/api/folders'
import FolderTreeNode from './FolderTreeNode.vue'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{
  projectActions?: string[]
  projectId: string
  visible?: boolean
  sidebar?: boolean
  navigationActive?: boolean
  canWrite: boolean
  canUpload: boolean
  canDownload: boolean
  canGenerate?: boolean
}>()
const emit = defineEmits<{ create: []; select: []; reference: [asset: Asset, kind: 'image' | 'video']; selectionChange: [count: number] }>()
const assetRefreshKey = ref(0)
const {
  active,
  assetCounts,
  rows,
  roots,
  crumbs,
  children,
  expanded,
  currentId,
  loading,
  pending: writing,
  saveLocked: pending,
  saveUncertain,
  transferUncertain,
  error,
  search,
  sort,
  page,
  total,
  trash,
  recycled,
  dialog,
  closeEditor,
  form,
  fields,
  editing,
  dialogError,
  treeNext,
  loadTree,
  toggle,
  refresh,
  navigate: navigateFolder,
  showTrash: navigateTrash,
  filter,
  changePage,
  startCreate,
  startEdit,
  save,
  remove,
  restore,
  destinationOpen,
  destinationMode,
  destinationCrumbs,
  destinations,
  destinationHasNext,
  destinationLoading,
  destinationSearch,
  destinationSort,
  enterDestination,
  loadDestinations,
  chooseDestination,
  startDestination,
  startDestinationCreate,
  createInDestination,
  transfer,
} = useFolders(props.projectId, () => props.visible !== false)
function navigate(path: import('@/api/folders').Folder[]) { emit('select'); navigateFolder(path) }
function showTrash() { emit('select'); navigateTrash() }
const batchRestore = useFolderBatchRestore(() => recycled.value, () => props.canWrite && !pending.value, refresh)
const personal = useFolderPresentation(expanded, loadTree)
const orderedRoots = computed(() => personal.arrange(roots.value))
const orderedChildren = computed(() => Object.fromEntries(Object.entries(children).map(([id, values]) => [id, personal.arrange(values)])))
function refreshAll() {
  void refresh()
  assetRefreshKey.value++
}
defineExpose({ refreshAll })
watch(pending, (value, before) => {
  if (before && !value) assetRefreshKey.value++
})
const colors: { value: FolderColor; label: string }[] = [
  { value: 'lime', label: '青柠' },
  { value: 'cyan', label: '青色' },
  { value: 'slate', label: '岩灰' },
  { value: 'violet', label: '紫罗兰' },
  { value: 'purple', label: '紫色' },
  { value: 'pink', label: '粉色' },
  { value: 'yellow', label: '黄色' },
]
const rules: FormRules = {
  name: [
    { required: true, whitespace: true, message: '请输入目录名称', trigger: 'blur' },
    { max: 200, message: '名称最多200字符', trigger: 'blur' },
  ],
}
</script>
<template>
  <section class="folder-workspace">
    <Teleport to="#project-sidebar-tree" :disabled="!sidebar">
    <aside v-show="visible !== false" class="folder-sidebar" aria-label="项目文件夹">
      <div class="folder-sidebar-scroll">
      <div class="folder-heading">
        <span>文件夹</span
        ><button
          v-if="canWrite"
          class="folder-icon-button"
          :disabled="pending"
          aria-label="新建根目录"
          @click="startCreate(null)"
        >
          <IconPlus :size="18" />
        </button>
        <ElPopover v-if="sidebar" trigger="click" placement="right-start" :width="260">
          <template #reference><button class="folder-icon-button" aria-label="查找与排序文件夹"><IconSearch :size="16" /></button></template>
          <ElInput v-model="search" placeholder="搜索项目内目录" clearable aria-label="搜索目录" @input="filter" />
          <ElSelect v-model="sort" aria-label="目录排序" style="margin-top:10px" @change="filter"><ElOption label="名称 A–Z" value="nameAsc" /><ElOption label="名称 Z–A" value="nameDesc" /><ElOption label="最近修改" value="updatedDesc" /></ElSelect>
        </ElPopover>
      </div>
      <div v-if="sidebar && search" class="folder-search-results"><button v-for="folder in rows" :key="folder.id" class="folder-tree-label" @click="navigate([folder])"><IconFolder :size="18" />{{ folder.name }}</button><span v-if="!rows.length && !loading">无匹配目录</span><button v-if="total > page * 30" class="folder-text-button" @click="changePage(page + 1)">下一页</button></div>
      <button
        class="folder-tree-label folder-root"
        :class="{ active: navigationActive !== false && !currentId && !trash }"
        @click="navigate([])"
      >
        <IconFolder :size="19" />全部素材<span class="folder-asset-count">{{ assetCounts?.total ?? '—' }}</span>
      </button>
      <button v-if="canWrite" class="folder-tree-label folder-add" :disabled="pending" @click="startCreate(null)"><IconPlus :size="18" />添加文件夹</button>
      <ul class="folder-tree">
        <FolderTreeNode
          v-for="folder in orderedRoots"
          :key="folder.id"
          :folder="folder"
          :counts="assetCounts?.folders"
          :path="[]"
          :children="orderedChildren"
          :pinned="personal.pinned.value"
          :expanded="expanded"
          :current-id="navigationActive === false ? null : currentId"
          :can-write="canWrite"
          :pending="pending"
          :tree-next="treeNext"
          @navigate="navigate"
          @toggle="toggle"
          @create="startCreate" @edit="startEdit" @remove="remove"
          @move="startDestination($event, 'move')" @copy="startDestination($event, 'copy')"
          @more="loadTree($event, true)"
          @pin="personal.pin"
          @move-up="personal.moveUp($event.parentId ? children[$event.parentId] || [] : roots, $event.id)"
        />
      </ul>
      <p v-if="!sidebar" class="muted">置顶和顺序仅影响本人已加载的同级目录，点击“保存素材视图”保存。</p>
      <p v-if="personal.notice.value" role="status">{{ personal.notice.value }}</p>
      <button v-if="treeNext.root" class="folder-text-button" @click="loadTree(null, true)">
        加载更多目录
      </button>
      </div>
      <button
        v-if="canWrite"
        class="folder-tree-label folder-root folder-trash-entry"
        :class="{ active: navigationActive !== false && trash }"
        @click="showTrash"
      >
        <IconTrash :size="18" />回收站
      </button>
    </aside>
    </Teleport>
    <div class="folder-content">
      <header v-if="!sidebar || trash" class="folder-toolbar">
        <nav class="folder-breadcrumb" aria-label="目录路径">
          <button @click="navigate([])">全部</button>
          <template v-if="!trash"
            ><span v-for="(crumb, index) in crumbs" :key="crumb.id">
              /
              <button @click="navigate(crumbs.slice(0, index + 1))">{{ crumb.name }}</button></span
            ></template
          >
          <span v-else> / 回收站</span>
        </nav>
        <Button variant="ghost" :disabled="loading || pending" @click="refreshAll">刷新</Button>
        <Button
          v-if="canWrite && !trash"
          variant="outline"
          :disabled="pending"
          @click="startCreate(currentId)"
        >
          <IconPlus :size="16" />新建目录</Button
        >
      </header>
      <details v-if="!trash && !sidebar" class="folder-filter-details"><summary>查找与排序文件夹</summary><div class="folder-filters">
        <ElInput
          v-model="search"
          placeholder="搜索项目内目录"
          clearable
          aria-label="搜索目录"
          @input="filter"
        />
        <ElSelect v-model="sort" aria-label="目录排序" @change="filter">
          <ElOption label="名称 A–Z" value="nameAsc" /><ElOption
            label="名称 Z–A"
            value="nameDesc"
          />
          <ElOption label="最早创建" value="createdAsc" /><ElOption
            label="最新创建"
            value="createdDesc"
          />
          <ElOption label="最近修改" value="updatedDesc" />
        </ElSelect>
      </div>
      </details>
      <p v-if="error" class="project-error" role="alert">{{ error }}</p>
      <p v-if="loading" class="muted" role="status">正在加载目录…</p>
      <template v-else-if="trash">
        <p class="muted">目录可在删除后30天内恢复。恢复不会拉回已经移动到父级的内容。</p>
        <div v-if="canWrite" class="folder-actions">
          <ElCheckbox :model-value="batchRestore.allSelected.value" :disabled="pending || batchRestore.pending.value" @change="batchRestore.selectAll(Boolean($event))">选择当前页可恢复目录</ElCheckbox>
          <Button :disabled="pending || batchRestore.pending.value || !batchRestore.selected.value.length" @click="batchRestore.restore">{{ batchRestore.pending.value ? '正在恢复…' : `恢复所选（${batchRestore.selected.value.length}）` }}</Button>
        </div>
        <p v-if="batchRestore.message.value" role="status">{{ batchRestore.message.value }}</p>
        <div v-for="entry in recycled" :key="entry.id" class="folder-list-row">
          <ElCheckbox v-if="canWrite" :model-value="batchRestore.selected.value.includes(entry.id)" :aria-label="`选择恢复 ${entry.name}`" :disabled="pending || batchRestore.pending.value || !entry.canRestore" @change="batchRestore.toggle(entry.id, Boolean($event))" />
          <IconFolder :size="24" />
          <div class="folder-row-title">
            <strong>{{ entry.name }}</strong>
            <small>恢复期限 {{ formatProjectDate(entry.restoreUntil) }}</small>
          </div>
          <Button
            v-if="canWrite"
            variant="ghost"
            :disabled="pending || batchRestore.pending.value || !entry.canRestore"
            @click="restore(entry)"
          >
            {{ entry.canRestore ? '恢复' : '已过恢复期限' }}</Button
          >
        </div>
        <p v-if="!recycled.length" class="folder-empty">回收站暂无文件夹</p>
      </template>
      <template v-else-if="!sidebar">
        <div v-for="folder in rows" :key="folder.id" class="folder-list-row">
          <IconFolder :size="25" :class="'folder-color-' + folder.color" />
          <button
            class="folder-row-title"
            @click="navigate(search ? [folder] : [...crumbs, folder])"
          >
            <strong>{{ folder.name }}</strong
            ><small>{{ folder.description || '文件夹' }}</small>
          </button>
          <div v-if="canWrite" class="folder-actions">
            <button :disabled="pending" @click="startEdit(folder)">编辑</button>
            <button :disabled="pending" @click="startDestination(folder, 'move')">移动</button>
            <button :disabled="pending" @click="startDestination(folder, 'copy')">复制</button>
            <button :disabled="pending" @click="remove(folder)">删除</button>
          </div>
        </div>
        <div v-if="!rows.length && search" class="folder-empty">
          <IconFolder :size="42" />
          <h3>{{ search ? '没有匹配的目录' : '这里还没有子目录' }}</h3>
        </div>
      </template>
      <ElPagination
        v-if="total > 30 && (!sidebar || trash)"
        :current-page="page"
        :page-size="30"
        :total="total"
        layout="prev, pager, next"
        @current-change="changePage"
      />
      <ProjectAssets
        :compact="sidebar"
        :project-actions="projectActions"
        v-show="!trash"
        :visible="active && !trash"
        :project-id="projectId"
        :folder-id="currentId"
        :can-upload="canUpload && !trash"
        :can-download="canDownload"
        :can-generate="canGenerate"
        :can-move="canWrite && !trash"
        :refresh-key="assetRefreshKey"
        :folder-settings="personal.settings.value"
        @selection-change="emit('selectionChange', $event)"
        @restore-folders="personal.restore"
        @create="emit('create')" @reference="(asset, kind) => emit('reference', asset, kind)"
      >
        <template v-if="sidebar" #breadcrumb>
        <nav class="folder-breadcrumb" aria-label="目录路径">
          <button @click="navigate([])">全部</button>
          <template v-if="!trash"
            ><span v-for="(crumb, index) in crumbs" :key="crumb.id">
              /
              <button @click="navigate(crumbs.slice(0, index + 1))">{{ crumb.name }}</button></span
            ></template
          >
          <span v-else> / 回收站</span>
        </nav>
        </template>
      </ProjectAssets>
    </div>
    <ElDialog
      :model-value="active && dialog"
      :before-close="closeEditor"
      :title="editing ? '编辑文件夹' : createInDestination ? '新建目标文件夹' : '新建文件夹'"
      width="460px"
      :close-on-click-modal="!pending"
      :close-on-press-escape="!pending"
      :show-close="!pending"
    >
      <template #header="{ titleId, titleClass }">
        <DialogHeading :title-id="titleId" :title-class="titleClass" :title="editing ? '编辑文件夹' : createInDestination ? '新建目标文件夹' : '新建文件夹'" />
      </template>
      <ElForm
        ref="form"
        :model="fields"
        :rules="rules"
        label-position="top"
        :disabled="pending || !canWrite"
      >
        <ElFormItem label="名称" prop="name"
          ><ElInput v-model="fields.name" maxlength="200"
        /></ElFormItem>
        <ElFormItem label="描述"
          ><ElInput v-model="fields.description" type="textarea" :rows="3"
        /></ElFormItem>
        <ElFormItem label="颜色"
          ><div class="folder-colors">
            <button
              v-for="color in colors"
              :key="color.value"
              type="button"
              :disabled="pending || !canWrite"
              :class="['folder-color-' + color.value, { selected: fields.color === color.value }]"
              :aria-label="color.label"
              :aria-pressed="fields.color === color.value"
              @click="fields.color = color.value"
            >
              <IconFolder :size="26" />
            </button></div
        ></ElFormItem>
      </ElForm>
      <p v-if="transferUncertain" role="status">目录移动或复制结果尚未确认，请重试原请求；确认前暂不能更换目标或关闭。</p>
      <p v-if="saveUncertain" role="status">目录保存结果尚未确认，请重试原请求，确认前暂不能修改或关闭。</p>
      <p v-if="dialogError" class="project-error" role="alert">{{ dialogError }}</p>
      <template #footer
        ><Button variant="ghost" :disabled="pending" @click="closeEditor">取消</Button>
        <Button :disabled="writing || !canWrite || (!saveUncertain && !fields.name.trim())" @click="save">{{
          writing ? '保存中…' : saveUncertain ? '重试确认原请求' : '保存'
        }}</Button></template
      >
    </ElDialog>
    <ElDialog
      :model-value="active && destinationOpen" @update:model-value="active && (destinationOpen = $event)"
      :title="destinationMode === 'move' ? '移动到' : '复制到'"
      width="500px"
      :close-on-click-modal="!pending"
      :close-on-press-escape="!pending"
      :show-close="!pending"
    >
      <template #header="{ titleId, titleClass }">
        <DialogHeading :title-id="titleId" :title-class="titleClass" :title="destinationMode === 'move' ? '移动到' : '复制到'" />
      </template>
      <nav class="folder-breadcrumb">
        <button :disabled="pending" @click="chooseDestination([])">项目根目录</button>
        <span v-for="(folder, index) in destinationCrumbs" :key="folder.id">
          /
          <button
            :disabled="pending"
            @click="chooseDestination(destinationCrumbs.slice(0, index + 1))"
          >
            {{ folder.name }}
          </button></span
        >
      </nav>
      <div class="folder-destination-filters">
        <ElInput v-model="destinationSearch" aria-label="搜索目标目录" placeholder="搜索项目内目标目录" clearable :disabled="pending" @keyup.enter="loadDestinations()" @clear="loadDestinations()" />
        <ElSelect v-model="destinationSort" aria-label="目标目录排序" :disabled="pending" @change="loadDestinations()">
          <ElOption label="名称 A–Z" value="nameAsc" />
          <ElOption label="名称 Z–A" value="nameDesc" />
          <ElOption label="最新创建" value="createdDesc" />
          <ElOption label="最早创建" value="createdAsc" />
          <ElOption label="最近更新" value="updatedDesc" />
        </ElSelect>
        <Button variant="ghost" :disabled="pending" @click="loadDestinations()">搜索目标</Button>
      </div>
      <p v-if="destinationSearch.trim()" class="muted">搜索结果来自项目内目录，请进入目标目录后确认。</p>
      <Button v-if="canWrite" variant="outline" :disabled="pending || destinationLoading || Boolean(destinationSearch.trim())" @click="startDestinationCreate">在当前位置新建文件夹</Button>
      <p v-if="destinationLoading" role="status">正在加载…</p>
      <button
        v-for="folder in destinations"
        :key="folder.id"
        class="folder-destination"
        :disabled="pending || destinationLoading"
        @click="enterDestination(folder)"
      >
        <IconFolder :size="20" />{{ folder.name }}
      </button>
      <button
        v-if="destinationHasNext"
        class="folder-text-button"
        :disabled="destinationLoading || pending"
        @click="loadDestinations(true)"
      >
        加载更多
      </button>
      <p v-if="transferUncertain" role="status">目录移动或复制结果尚未确认，请重试原请求；确认前暂不能更换目标或关闭。</p>
      <p v-if="saveUncertain" role="status">目录保存结果尚未确认，请重试原请求，确认前暂不能修改或关闭。</p>
      <p v-if="dialogError" class="project-error" role="alert">{{ dialogError }}</p>
      <template #footer
        ><Button variant="ghost" :disabled="pending" @click="destinationOpen = false">取消</Button>
        <Button :disabled="writing || saveUncertain || destinationLoading || Boolean(destinationSearch.trim()) || !canWrite" @click="transfer">{{
          writing ? '处理中…' : transferUncertain ? '重试确认原请求' : '选择当前位置'
        }}</Button></template
      >
    </ElDialog>
  </section>
</template>



