<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog, ElForm, ElFormItem, ElInput, ElAlert } from 'element-plus'
import { computed } from 'vue'
import type { Project } from '@/api/projects'
import { useProjectLifecycle } from '@/composables/useProjectLifecycle'
import Button from '@/components/ui/Button.vue'
const emit = defineEmits<{ changed: [project: Project] }>()
const { open, target, action, form, fields, rules, loading, saving, uncertain, ready, locked, error, start, close, load, save } =
  useProjectLifecycle(project => emit('changed', project))
const presentation = computed(() => ({
  rename: { title: '编辑项目名称', label: '', submit: '保存名称', help: '' },
  archive: { title: '归档项目', label: '归档原因', submit: '确认归档', help: '适用于已结束的项目。归档后所有成员仅可查看，素材和历史记录保留，已受理的生成任务不会取消。之后可恢复项目。' },
  restore: { title: '恢复项目', label: '恢复原因（可选）', submit: '确认恢复', help: '项目将恢复为进行中，成员可按权限继续创作和编辑，不会重新提交旧任务。' },
  pause: { title: '暂停创作', label: '暂停原因', submit: '确认暂停创作', help: '所有成员将暂时无法新建生成任务或进行普通编辑，仍可查看。已受理的生成任务不会取消，之后可恢复创作。' },
  resume: { title: '恢复创作', label: '恢复原因（可选）', submit: '确认恢复创作', help: '成员可按权限继续创作和编辑，不会重新提交旧任务。' },
})[action.value])
defineExpose({ start })
</script>
<template>
  <ElDialog :model-value="open" :title="presentation.title" width="480px" align-center
    :close-on-click-modal="false" :close-on-press-escape="!locked" :show-close="!locked" :before-close="() => close()">
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" :title="presentation.title" />
    </template>
    <p v-if="action !== 'rename'">{{ target?.name }}</p>
    <p v-if="presentation.help" class="muted">{{ presentation.help }}</p>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <ElAlert v-if="uncertain && !saving" title="操作结果尚未确认。请重试同一请求，确认前不能更改内容或离开。" type="warning" :closable="false" />
    <p v-if="loading" role="status">正在核对项目状态与权限…</p>
    <ElForm ref="form" :model="fields" :rules="rules" label-position="top" :disabled="locked || !ready">
      <ElFormItem v-if="action === 'rename'" label="项目名称" prop="name">
        <ElInput v-model="fields.name" :maxlength="200" show-word-limit />
      </ElFormItem>
      <ElFormItem v-else :label="presentation.label" prop="reason">
        <ElInput v-model="fields.reason" type="textarea" :rows="3" :maxlength="4000" show-word-limit />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <Button variant="ghost" :disabled="locked" @click="close">取消</Button>
      <Button v-if="!ready && !locked" variant="outline" :disabled="loading" @click="load()">重新核对</Button>
      <Button :disabled="saving || loading || !ready" @click="save">{{ saving ? '正在处理…' : uncertain ? '重试同一请求' : presentation.submit }}</Button>
    </template>
  </ElDialog>
</template>
