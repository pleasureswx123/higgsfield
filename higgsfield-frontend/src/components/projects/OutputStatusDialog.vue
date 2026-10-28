<script setup lang="ts">
import { ref } from 'vue'
import { ElDialog, ElForm, ElFormItem, ElInput, ElSelect, ElOption, type FormInstance } from 'element-plus'
import type { GenerationOutput } from '@/api/generations'
import { useOutputStatus } from '@/composables/useOutputStatus'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps<{ output?: GenerationOutput }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const state = useOutputStatus(() => props.output, () => emit('saved'), () => emit('close'))
const form = ref<FormInstance>()
const names = { none: '未设置', working: '制作中', review: '待审核', approved: '已通过', rejected: '已拒绝' }
function close() { if (!state.pending.value) emit('close') }
async function submit() {
  await state.submit(async () => !!(await form.value?.validate().catch(() => false)))
}
</script>

<template>
  <ElDialog :model-value="!!output" title="修改作品工作状态" width="min(520px, 94vw)"
    :close-on-click-modal="false" :close-on-press-escape="!state.pending.value"
    :show-close="!state.pending.value" :before-close="close">
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="修改作品工作状态" />
    </template>
    <p class="muted">这是协作标签。修改不会重新生成，不改变归档或费用状态。</p>
    <ElForm ref="form" :model="{ status: state.status.value, reason: state.reason.value }" label-position="top" @submit.prevent>
      <ElFormItem label="工作状态" prop="status" :rules="[{ required: true, message: '请选择工作状态' }]">
        <ElSelect v-model="state.status.value" :disabled="state.pending.value || state.retryable.value || !state.allowed.value">
          <ElOption v-for="(label, value) in names" :key="value" :value="value" :label="label" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="变更说明（选填）" prop="reason" :rules="[{ max: 4000, message: '说明最多4000字' }]">
        <ElInput v-model="state.reason.value" type="textarea" maxlength="4000" show-word-limit
          :disabled="state.pending.value || state.retryable.value || !state.allowed.value" />
      </ElFormItem>
    </ElForm>
    <p v-if="state.error.value" class="status-error" role="alert">{{ state.error.value }}</p>
    <Button v-if="state.error.value && !state.retryable.value" variant="ghost" :disabled="state.pending.value" @click="state.reload">载入当前状态（清除本次编辑）</Button>
    <template #footer>
      <Button variant="ghost" :disabled="state.pending.value" @click="close">关闭</Button>
      <Button :disabled="state.pending.value || (!state.allowed.value && !state.retryable.value)" @click="submit">
        {{ state.pending.value ? '正在保存…' : state.retryable.value ? '重试确认保存结果' : '保存状态' }}
      </Button>
    </template>
  </ElDialog>
</template>

<style scoped>
.status-error { margin: 12px 0; color: var(--destructive); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
</style>
