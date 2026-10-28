<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import '@/styles/folders.css'
import { ElDialog, ElForm, ElFormItem, ElInput, ElSelect, ElOption } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useDirectoryMove } from '@/composables/useDirectoryMove'
const props = withDefaults(
  defineProps<{
    projectId: string
    allowed: boolean
    canCreateFolder?: boolean
    visible?: boolean
    kind?: 'media' | 'element'
    operation?: 'move' | 'copy'
  }>(),
  { operation: 'move', kind: 'media', canCreateFolder: false, visible: true },
)
const emit = defineEmits<{ changed: [ids: string[], summary: string] }>()
const {
  q,
  createOpen,
  createForm,
  newFolder,
  creating,
  createUncertain,
  startCreate,
  cancelCreate,
  submitCreate,
  sort,
  searching,
  search,
  changeSort,
  selectFolder,
  active,
  entry,
  entries,
  report,
  path,
  rows,
  loading,
  saving,
  uncertain,
  hasNext,
  error,
  locked,
  open,
  openMany,
  navigate,
  close,
  load,
  save,
} = useDirectoryMove(
  props.projectId,
  () => props.allowed,
  (ids, summary) => emit('changed', ids, summary),
  props.kind,
  () => props.canCreateFolder,
  () => props.visible,
  props.operation,
)
const actionLabel = props.operation === 'copy' ? '复制' : '移动'
defineExpose({ open, openMany, locked })
</script>
<template>
  <ElDialog
    append-to-body
    :model-value="active && allowed && Boolean(entry)"
    :title="`${actionLabel}${kind === 'element' ? '元素' : '素材'}：${entries.length > 1 ? `${entries.length} 项` : entry?.name || ''}`"
    width="min(520px,94vw)"
    :show-close="!locked"
    :close-on-click-modal="!locked"
    :close-on-press-escape="!locked"
    :before-close="close"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" :title="`${actionLabel}${kind === 'element' ? '元素' : '素材'}：${entries.length > 1 ? `${entries.length} 项` : entry?.name || ''}`" />
    </template>
    <p v-if="entries.length > 1" class="muted">同一项目内逐项{{ actionLabel }}；部分失败不会撤销成功项。</p>
    <p v-if="report" role="status">{{ report }}</p>
    <nav class="folder-breadcrumb" aria-label="移动目标路径">
      <button :disabled="locked || !allowed" @click="navigate([])">项目根目录</button>
      <span v-for="(folder, index) in path" :key="folder.id">
        /
        <button :disabled="locked || !allowed" @click="navigate(path.slice(0, index + 1))">
          {{ folder.name }}
        </button></span
      >
    </nav>
    <div class="destination-search">
      <ElInput
        v-model="q"
        aria-label="搜索移动目标目录"
        placeholder="搜索本项目目录"
        :disabled="locked || !allowed"
        @keyup.enter="search"
      />
      <Button variant="outline" :disabled="locked || !allowed" @click="search">搜索</Button>
      <ElSelect
        :model-value="sort"
        aria-label="移动目标排序"
        :disabled="locked || !allowed"
        @update:model-value="changeSort"
      >
        <ElOption label="名称 A-Z" value="nameAsc" /><ElOption label="名称 Z-A" value="nameDesc" />
        <ElOption label="最早创建" value="createdAsc" /><ElOption
          label="最新创建"
          value="createdDesc"
        /><ElOption label="最近修改" value="updatedDesc" />
      </ElSelect>
    </div>
    <p v-if="searching" class="muted">搜索结果来自本项目。请进入目标目录后确认移动。</p>
    <Button
      v-if="canCreateFolder && !createOpen"
      variant="outline"
      :disabled="locked || loading || searching || !allowed"
      @click="startCreate"
      >在当前位置新建目录</Button
    >
    <ElForm
      v-if="createOpen"
      ref="createForm"
      :model="newFolder"
      label-position="top"
      :disabled="locked || !canCreateFolder || !allowed"
    >
      <ElFormItem
        label="目录名称"
        prop="name"
        :rules="[{ required: true, whitespace: true, message: '请输入目录名称' }]"
      >
        <ElInput v-model="newFolder.name" maxlength="200" />
      </ElFormItem>
      <ElFormItem label="描述"
        ><ElInput v-model="newFolder.description" type="textarea" maxlength="2000"
      /></ElFormItem>
      <ElFormItem label="目录颜色"
        ><ElSelect v-model="newFolder.color">
          <ElOption
            v-for="option in [
              { value: 'lime', label: '青柠' },
              { value: 'cyan', label: '青色' },
              { value: 'slate', label: '灰蓝' },
              { value: 'violet', label: '蓝紫' },
              { value: 'purple', label: '紫色' },
              { value: 'pink', label: '粉色' },
              { value: 'yellow', label: '黄色' },
            ]"
            :key="option.value"
            :value="option.value"
            :label="option.label"
          /> </ElSelect
      ></ElFormItem>
    </ElForm>
    <div v-if="createOpen">
      <p v-if="createUncertain" role="status">目录创建结果尚未确认，重试沿用原目录内容与位置。</p>
      <Button variant="ghost" :disabled="locked" @click="cancelCreate">取消新建</Button>
      <Button
        :disabled="
          creating ||
          saving ||
          uncertain ||
          !canCreateFolder ||
          !allowed ||
          (!createUncertain && !newFolder.name.trim())
        "
        @click="submitCreate"
        >{{ creating ? '创建中…' : createUncertain ? '重试确认原请求' : '创建并进入' }}</Button
      >
    </div>
    <p v-if="loading" role="status">正在读取目录…</p>
    <button
      v-for="folder in rows"
      :key="folder.id"
      class="folder-destination"
      :disabled="locked || !allowed"
      @click="selectFolder(folder)"
    >
      {{ folder.name }}
    </button>
    <p v-if="!loading && !rows.length && !error" class="muted">
      {{ searching ? '没有匹配目录。' : '当前目录没有子目录，可选择当前位置。' }}
    </p>
    <button
      v-if="hasNext"
      class="folder-text-button"
      :disabled="loading || locked || !allowed"
      @click="load(true)"
    >
      加载更多目录
    </button>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <template #footer
      ><Button variant="ghost" :disabled="locked" @click="close">取消</Button
      ><Button
        :disabled="
          saving || creating || createOpen || createUncertain || loading || searching || !allowed
        "
        @click="save"
        >{{ saving ? `${actionLabel}中…` : uncertain ? '重试同一请求' : `${actionLabel}到当前位置` }}</Button
      ></template
    >
  </ElDialog>
</template>

<style scoped>
.destination-search {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}
.destination-search .el-input {
  flex: 1;
  min-width: 160px;
}
.destination-search .el-select {
  width: 140px;
}
</style>
