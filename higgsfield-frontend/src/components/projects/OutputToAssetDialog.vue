<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog, ElForm, ElFormItem, ElInput, ElPagination, type FormRules } from 'element-plus'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import { useOutputToAsset } from '@/composables/useOutputToAsset'
const props = defineProps<{ outputId: string; projectId: string }>()
const emit = defineEmits<{ close: [] }>()
const {
  form,
  fields,
  projects,
  search,
  page,
  total,
  folders,
  trail,
  folderPage,
  folderTotal,
  loading,
  checking,
  folderLoading,
  saving,
  allowed,
  error,
  result,
  uncertain,
  locked,
  canClose,
  filter,
  loadFolders,
  enter,
  submit,
} = useOutputToAsset(props.outputId, props.projectId)
const rules: FormRules = {
  projectId: [{ required: true, message: '请选择目标项目' }],
  name: [{ required: true, whitespace: true, message: '请输入素材名称' }],
}
function close() {
  if (canClose.value) emit('close')
}
</script>
<template>
  <ElDialog
    :model-value="true"
    title="作品转素材"
    width="min(720px, 94vw)"
    append-to-body
    :before-close="close"
    :show-close="canClose"
    :close-on-click-modal="false"
    :close-on-press-escape="canClose"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="作品转素材" />
    </template>
    <template v-if="result">
      <p role="status">已创建素材“{{ result.name }}”，原作品和任务记录保留。</p>
      <RouterLink
        :to="{
          name: 'project-detail',
          params: { id: fields.projectId },
          query: { tab: 'folders' },
        }"
        >打开目标项目素材库</RouterLink
      >
    </template>
    <ElForm
      v-else
      ref="form"
      :model="fields"
      :rules="rules"
      label-position="top"
      :disabled="locked"
    >
      <p class="muted">复用已归档文件，创建独立素材及首个版本，不会重新生成或向供应商发起调用。</p>
      <ElFormItem label="目标项目" prop="projectId">
        <div class="output-target">
          <div class="element-toolbar">
            <ElInput
              v-model="search"
              placeholder="搜索活跃项目"
              clearable
              @keyup.enter="filter"
              @clear="filter"
            /><Button variant="ghost" :disabled="locked" @click="filter">搜索</Button>
          </div>
          <p v-if="loading" role="status">正在加载项目…</p>
          <button
            v-for="project in projects"
            :key="project.id"
            type="button"
            class="output-project"
            :class="{ active: fields.projectId === project.id }"
            :aria-pressed="fields.projectId === project.id"
            :disabled="locked"
            @click="fields.projectId = project.id"
          >
            {{ project.name }}
          </button>
          <ElPagination
            v-if="total > 10"
            v-model:current-page="page"
            :total="total"
            :page-size="10"
            :disabled="locked"
            layout="prev, pager, next"
          />
          <p class="muted">已选项目 ID：{{ fields.projectId }}</p>
        </div>
      </ElFormItem>
      <p v-if="checking" role="status">正在核验目标项目权限…</p>
      <ElFormItem v-if="allowed" label="目标目录">
        <div class="output-target">
          <p>
            根目录<span v-for="folder in trail" :key="folder.id"> / {{ folder.name }}</span>
          </p>
          <Button v-if="trail.length" variant="ghost" :disabled="locked" @click="enter()"
            >返回上级</Button
          >
          <p v-if="folderLoading" role="status">正在加载子目录…</p>
          <button
            v-for="folder in folders"
            :key="folder.id"
            type="button"
            class="output-project"
            :disabled="locked"
            @click="enter(folder)"
          >
            进入 {{ folder.name }}
          </button>
          <p v-if="!folderLoading && !folders.length" class="muted">当前目录没有子目录。</p>
          <ElPagination
            v-if="folderTotal > 20"
            v-model:current-page="folderPage"
            :page-size="20"
            :total="folderTotal"
            :disabled="locked"
            layout="prev, pager, next"
            @current-change="loadFolders"
          />
          <p class="muted">素材将保存到当前显示的目录。</p>
        </div>
      </ElFormItem>
      <ElFormItem label="素材名称" prop="name"
        ><ElInput v-model="fields.name" maxlength="200"
      /></ElFormItem>
    </ElForm>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="uncertain" role="status">
      上次入库结果尚未确认，请重试原请求，确认前不能修改目标或再次创建。
      <span v-if="canClose">当前无法核验目标权限，可以关闭；本次登录内恢复权限并重新打开同一作品后，可重试原请求。刷新页面或退出登录会清除本地恢复记录，届时应先核查目标素材库。</span>
    </p>
    <template #footer>
      <Button variant="ghost" :disabled="!canClose" @click="close">关闭</Button>
      <Button v-if="!result" :disabled="saving || checking || !allowed" @click="submit">{{
        saving ? '入库中…' : uncertain ? '重试确认入库结果' : '确认入库'
      }}</Button>
    </template>
  </ElDialog>
</template>
<style scoped>
.output-target {
  width: 100%;
}
.output-project {
  padding: 8px 12px;
  margin: 0 8px 8px 0;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--foreground);
  border-radius: 8px;
  cursor: pointer;
}
.output-project.active,
.output-project:hover {
  background: var(--surface-hover);
}
.output-project.active {
  border-color: var(--primary);
}
.output-project:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
