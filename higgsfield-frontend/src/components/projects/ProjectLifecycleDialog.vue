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
  rename: { title: '编辑项目名称', label: '', submit: '保存名称', help: '修改名称不改变项目身份、素材归属或历史费用。' },
  archive: { title: '归档项目', label: '归档原因', submit: '确认归档', help: '归档后项目只读，已有供应商任务及历史费用保留。未保存简报仍保留在当前页面。' },
  restore: { title: '恢复项目', label: '恢复原因（可选）', submit: '确认恢复', help: '恢复后可按当前权限继续工作。旧任务不会重新提交，新生成仍需通过配置和预算校验。' },
  pause: { title: '暂停项目', label: '暂停原因', submit: '确认暂停', help: '暂停后停止新创作与普通编辑，已受理任务继续维护，历史费用保留。未保存简报仍保留在当前页面。' },
  resume: { title: '恢复项目运行', label: '恢复原因（可选）', submit: '确认恢复运行', help: '恢复后按当前权限继续工作。旧任务不会重新提交，新任务仍需通过配置和预算校验。' },
})[action.value])
defineExpose({ start })
</script>
<template>
  <ElDialog :model-value="open" :title="presentation.title" width="480px" align-center
    :close-on-click-modal="false" :close-on-press-escape="!locked" :show-close="!locked" :before-close="() => close()">
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" :title="presentation.title" />
    </template>
    <p>{{ target?.name }}</p>
    <p class="muted">{{ presentation.help }}</p>
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
