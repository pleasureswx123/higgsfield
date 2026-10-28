<script setup>
import { useModelProfileEditor } from '@/composables/studio/useModelProfileEditor'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, error, formRef, form, start, close, submit } =
  useModelProfileEditor(() => emit('saved'))
defineExpose({ start })
const rules = {
  connectionId: [
    {
      required: true,
      validator: (_rule, value, callback) =>
        callback(
          /^[1-9]\d{0,18}$/.test(value) && BigInt(value) <= 9223372036854775807n
            ? undefined
            : new Error('请输入有效的供应商连接ID')
        ),
      trigger: 'blur',
    },
  ],
  code: [
    {
      required: true,
      pattern: /^[a-z][a-z0-9_-]{0,99}$/,
      message: '稳定码以小写字母开头，仅含小写字母、数字、下划线和短横线，最多100字符',
      trigger: 'blur',
    },
  ],
  displayName: [
    {
      required: true,
      validator: (_rule, value, callback) =>
        callback(
          value.trim() && value.length <= 200 && !/[\u0000-\u001f]/.test(value)
            ? undefined
            : new Error('请输入模型名称，最多200字符且不含控制字符')
        ),
      trigger: 'blur',
    },
  ],
  kind: [{ required: true, message: '请选择模型类型', trigger: 'change' }],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    title="登记模型身份"
    width="min(580px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    @close="close"
    destroy-on-close
  >
    <p>
      模型身份归属于一个供应商连接。登记后需继续配置能力版本和精确规格，并完成验证、发布、路由和价格配置。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      :disabled="pending"
    >
      <el-form-item
        label="供应商连接ID"
        prop="connectionId"
        ><el-input v-model="form.connectionId"
      /></el-form-item>
      <el-form-item
        label="连接内稳定码"
        prop="code"
        ><el-input
          v-model="form.code"
          maxlength="100"
          placeholder="例如 image-model-a"
      /></el-form-item>
      <el-form-item
        label="显示名称"
        prop="displayName"
        ><el-input
          v-model="form.displayName"
          maxlength="200"
      /></el-form-item>
      <el-form-item
        label="模型类型"
        prop="kind"
        ><el-radio-group v-model="form.kind"
          ><el-radio value="image">图片</el-radio
          ><el-radio value="video">视频</el-radio></el-radio-group
        ></el-form-item
      >
    </el-form>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    />
    <template #footer
      ><el-button
        :disabled="pending"
        @click="close"
        >取消</el-button
      ><el-button
        type="primary"
        :disabled="!canWrite"
        :loading="pending"
        @click="submit"
        >登记</el-button
      ></template
    >
  </el-dialog>
</template>
<style scoped>
p {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
