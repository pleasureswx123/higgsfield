<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog, ElForm, ElFormItem, ElInput, ElPagination } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useElementBatchCopy } from '@/composables/useElementBatchCopy'
const props = defineProps<{ allowed: boolean; visible?: boolean }>()
const emit = defineEmits<{ changed: [ids: string[]] }>()
const {
  active,
  opened,
  fields,
  form,
  projects,
  search,
  page,
  total,
  loading,
  searching,
  checking,
  saving,
  error,
  eligible,
  locked,
  uncertain,
  remaining,
  open,
  close,
  filter,
  submit,
} = useElementBatchCopy(
  () => props.allowed,
  (ids) => emit('changed', ids),
  () => props.visible !== false,
)
const required = [{ required: true, whitespace: true, message: '请填写此项' }]
defineExpose({ open, locked })
</script>
<template>
  <ElDialog
    :model-value="opened && active"
    title="复制所选元素"
    class="batch-copy-dialog"
    top="5vh"
    width="min(760px, 94vw)"
    append-to-body
    :before-close="close"
    :show-close="!locked"
    :close-on-press-escape="!locked"
    :close-on-click-modal="false"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="复制所选元素" />
    </template>
    <div class="batch-copy-body">
      <p class="muted">
        逐项复制已保存的固定修订。成功项会保留，失败不会撤销已成功的复制；负责人和审核状态不继承。
      </p>
      <p v-if="loading" role="status">正在核验所选元素…</p>
      <ElForm ref="form" :model="fields" label-position="top" :disabled="locked || loading">
        <ElFormItem label="目标项目" prop="targetProjectId" :rules="required">
          <div class="element-copy-projects">
            <div class="element-toolbar">
              <ElInput
                v-model="search"
                placeholder="搜索可访问的活跃项目"
                clearable
                @keyup.enter="filter"
                @clear="filter"
              /><Button variant="ghost" :disabled="locked || loading" @click="filter">搜索</Button>
            </div>
            <p v-if="searching" role="status">正在加载项目…</p>
            <button
              v-for="project in projects"
              :key="project.id"
              type="button"
              class="element-copy-project"
              :class="{ active: fields.targetProjectId === project.id }"
              :aria-pressed="fields.targetProjectId === project.id"
              :disabled="locked || loading"
              @click="fields.targetProjectId = project.id"
            >
              {{ project.name }}
            </button>
            <ElPagination
              v-if="total > 10"
              v-model:current-page="page"
              :page-size="10"
              :total="total"
              layout="prev, pager, next"
              :disabled="locked || loading"
            />
            <p class="muted">
              已选：{{
                projects.find((project) => project.id === fields.targetProjectId)?.name ||
                fields.targetProjectId
              }}
            </p>
          </div>
        </ElFormItem>
        <article v-for="(item, index) in fields.items" :key="item.id" class="batch-copy-row">
          <p>元素 {{ item.id }} · 固定修订 {{ item.sourceRevisionId }}</p>
          <p v-if="item.result" role="status">
            已复制：{{ item.result.name }} · 新元素 {{ item.result.id }}
          </p>
          <template v-else>
            <ElFormItem
              :label="`新名称（${index + 1}）`"
              :prop="`items.${index}.name`"
              :rules="required"
              ><ElInput v-model="item.name" maxlength="200"
            /></ElFormItem>
            <ElFormItem
              :label="`新别名（${index + 1}）`"
              :prop="`items.${index}.alias`"
              :rules="required"
              ><ElInput v-model="item.alias" maxlength="100" placeholder="目标项目内唯一的别名"
            /></ElFormItem>
            <p v-if="item.error" class="project-error" role="alert">{{ item.error }}</p>
          </template>
        </article>
      </ElForm>
      <p v-if="checking" role="status">正在核验目标权限…</p>
      <p v-else-if="remaining.length && !eligible" class="muted">
        需要源元素复制权限、目标元素创建权限；跨项目包含图片时还需要目标素材创建权限。
      </p>
      <p v-if="error" class="project-error" role="alert">{{ error }}</p>
      <p v-if="fields.items.length" role="status">
        已复制 {{ fields.items.length - remaining.length }} 项，剩余 {{ remaining.length }} 项。
      </p>
    </div>
    <template #footer
      ><Button variant="ghost" :disabled="locked" @click="close">关闭</Button
      ><Button v-if="remaining.length" :disabled="saving || !eligible" @click="submit">{{
        saving ? '复制中…' : uncertain ? '重试未完成请求' : '复制未完成项'
      }}</Button></template
    >
  </ElDialog>
</template>
<style scoped>
.batch-copy-body {
  max-height: calc(90vh - 140px);
  overflow: auto;
}
.project-error {
  min-height: 0;
  padding: 8px 0;
  text-align: left;
}

.batch-copy-row {
  padding-block: 12px;
  border-top: 1px solid var(--border);
}
</style>
