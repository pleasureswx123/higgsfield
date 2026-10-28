<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog, ElForm, ElFormItem, ElInput, ElPagination, type FormRules } from 'element-plus'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import type { ElementDetail } from '@/api/elements'
import { useElementCopy } from '@/composables/useElementCopy'
const props = defineProps<{ source: ElementDetail; visible?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const {
  active,
  locked,
  confirmClose,
  uncertain,
  form,
  fields,
  projects,
  search,
  projectPage,
  total,
  loading,
  checking,
  saving,
  error,
  permissionError,
  result,
  eligible,
  projectName,
  filter,
  submit,
} = useElementCopy(props.source, () => props.visible !== false)
const rules: FormRules = {
  targetProjectId: [{ required: true, message: '请选择目标项目' }],
  name: [{ required: true, whitespace: true, message: '请输入名称' }],
  alias: [{ required: true, whitespace: true, message: '请输入目标项目内唯一别名' }],
}
async function close() {
  if (await confirmClose()) emit('close')
}
defineExpose({ locked })
</script>
<template>
  <ElDialog
    :model-value="active"
    title="受控复制元素"
    width="min(700px, 94vw)"
    append-to-body
    :before-close="close"
    :show-close="!locked"
    :close-on-press-escape="!locked"
    :close-on-click-modal="false"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="受控复制元素" />
    </template>
    <template v-if="result"
      ><p role="status">已复制“{{ result.name }}”到{{ projectName }}。新元素 ID：{{ result.id }}</p>
      <RouterLink
        :to="{
          name: 'project-detail',
          params: { id: result.projectId },
          query: { tab: 'elements' },
        }"
        >打开目标项目元素</RouterLink
      ></template
    >
    <template v-else>
      <p class="muted">
        复制已保存的内部修订 #{{
          source.currentRevision.revisionNo
        }}，不包含编辑器中的未保存修改。目标创建新身份，负责人和审核状态不继承。
      </p>
      <ElForm ref="form" :model="fields" :rules="rules" label-position="top" :disabled="locked">
        <ElFormItem label="目标项目" prop="targetProjectId"
          ><div class="element-copy-projects">
            <div class="element-toolbar">
              <ElInput
                v-model="search"
                placeholder="搜索可访问的活跃项目"
                clearable
                @keyup.enter="filter"
                @clear="filter"
              /><Button type="button" variant="ghost" :disabled="locked" @click="filter"
                >搜索</Button
              >
            </div>
            <p v-if="loading" role="status">正在加载项目…</p>
            <button
              v-for="project in projects"
              :key="project.id"
              type="button"
              class="element-copy-project"
              :class="{ active: fields.targetProjectId === project.id }"
              :aria-pressed="fields.targetProjectId === project.id"
              :disabled="locked"
              @click="fields.targetProjectId = project.id"
            >
              {{ project.name }}</button
            ><ElPagination
              v-if="total > 10"
              v-model:current-page="projectPage"
              :page-size="10"
              :total="total"
              :disabled="locked"
              layout="prev, pager, next"
            />
            <p class="muted">已选：{{ projectName }}</p>
          </div></ElFormItem
        >
        <ElFormItem label="新名称" prop="name"
          ><ElInput v-model="fields.name" maxlength="200"
        /></ElFormItem>
        <ElFormItem label="新别名" prop="alias"
          ><ElInput v-model="fields.alias" maxlength="100" placeholder="目标项目内唯一的别名"
        /></ElFormItem>
      </ElForm>
      <p v-if="checking" role="status">正在核验目标创建权限…</p>
      <p v-if="permissionError" class="project-error" role="alert">{{ permissionError }}</p>
      <p class="muted">
        跨项目时复制固定图片版本并保留来源；目标同名属性不兼容时，会创建独立来源属性。服务端提交时再次核验双方权限。
      </p>
    </template>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <template #footer
      ><Button variant="ghost" :disabled="locked" @click="close">关闭</Button
      ><Button v-if="!result" :disabled="saving || !eligible" @click="submit">{{
        saving ? '复制中…' : uncertain ? '重试同一请求' : '确认复制'
      }}</Button></template
    >
  </ElDialog>
</template>
