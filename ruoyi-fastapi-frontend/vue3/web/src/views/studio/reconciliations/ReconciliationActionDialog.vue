<script setup>
import { ref } from 'vue'
defineProps({ target: Object, pending: Boolean, error: String, model: { type: Object, required: true }, allowed: Boolean })
const emit = defineEmits(['close', 'submit', 'update:subjectId', 'update:reason'])
const formRef = ref()
defineExpose({ validate: () => formRef.value?.validate() })
const rules = {
  subjectId: [{ required: true, message: '请输入计费对象ID', trigger: 'blur' }],
  reason: [{ required: true, whitespace: true, message: '请填写核对依据', trigger: 'blur' }],
}
</script>

<template>
  <el-dialog :model-value="!!target" :title="target?.action === 'resolve' ? '处理账单差异' : target?.action === 'match' ? '匹配计费对象' : '确认账单项'"
    width="min(640px, 95vw)" :show-close="!pending" :close-on-click-modal="!pending"
    :close-on-press-escape="!pending" @close="emit('close')">
    <template v-if="target">
      <p>账单项 {{ target.externalLineKey }} · {{ target.amount }} {{ target.currency }}</p>
      <p v-if="target.action === 'confirm'">将确认已匹配的计费对象 {{ target.subjectId }}。此操作不会自动调整估值。</p>
      <p v-else-if="target.action === 'resolve'">采用本次文件观察 {{ target.observationId }}：{{ target.sourceAmount }} {{ target.sourceCurrency }}。首次金额和全部导入证据保留，处理后仍需确认，不自动调整费用。</p>
      <p v-else>请核对同一供应商账号下的计费对象ID；平台不会根据相似名称自动匹配。</p>
      <el-form ref="formRef" :model="model" :rules="rules" :disabled="pending || !allowed" label-position="top">
        <el-form-item v-if="target.action !== 'confirm'" label="计费对象ID" prop="subjectId">
          <el-input :model-value="model.subjectId" maxlength="19" @update:model-value="emit('update:subjectId', $event)" />
        </el-form-item>
        <el-form-item label="操作依据" prop="reason"><el-input :model-value="model.reason" type="textarea"
          :rows="4" maxlength="2000" show-word-limit @update:model-value="emit('update:reason', $event)" /></el-form-item>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
    </template>
    <template #footer><el-button :disabled="pending" @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="pending" :disabled="!allowed" @click="emit('submit')">{{ target?.action === 'resolve' ? '采用此行证据' : target?.action === 'match' ? '保存匹配' : '确认账单项' }}</el-button></template>
  </el-dialog>
</template>
