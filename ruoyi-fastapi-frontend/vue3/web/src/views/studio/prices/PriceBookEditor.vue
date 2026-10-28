<script setup>
import { usePriceBookEditor } from '@/composables/studio/usePriceBookEditor'
import { validRoutingId } from '@/utils/routing'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, error, formRef, form, start, close, submit } = usePriceBookEditor(
  () => emit('saved')
)
defineExpose({ start })
const idRule = {
  validator: (_rule, value, callback) =>
    callback(validRoutingId(value) ? undefined : new Error('请输入有效ID')),
  trigger: 'blur',
}
const rules = {
  modelVariantId: [idRule],
  accountId: [
    {
      validator: (_rule, value, callback) =>
        callback(
          form.purpose !== 'procurement' || validRoutingId(value)
            ? undefined
            : new Error('采购价必须指定有效账号ID')
        ),
      trigger: 'blur',
    },
  ],
  purpose: [{ required: true, message: '请选择价格用途', trigger: 'change' }],
  currency: [
    { required: true, pattern: /^[A-Z]{3}$/, message: '币种须为三个大写字母', trigger: 'blur' },
  ],
  name: [
    {
      validator: (_rule, value, callback) =>
        callback(
          value.trim() && value.length <= 200 ? undefined : new Error('请输入名称，最多200字符')
        ),
      trigger: 'blur',
    },
  ],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    title="登记价格簿"
    width="min(560px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    destroy-on-close
    @close="close"
  >
    <p>
      价格簿绑定精确规格与币种。采购账号必须属于模型连接及相同区域；登记后还需配置价格版本、来源和生效区间。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="pending"
      label-position="top"
    >
      <el-form-item
        label="精确规格ID"
        prop="modelVariantId"
        ><el-input v-model="form.modelVariantId"
      /></el-form-item>
      <el-form-item
        label="名称"
        prop="name"
        ><el-input
          v-model="form.name"
          maxlength="200"
      /></el-form-item>
      <el-form-item
        label="用途"
        prop="purpose"
        ><el-select v-model="form.purpose"
          ><el-option
            label="平台价"
            value="platform" /><el-option
            label="采购价"
            value="procurement" /></el-select
      ></el-form-item>
      <el-form-item
        v-if="form.purpose === 'procurement'"
        label="采购账号ID"
        prop="accountId"
        ><el-input v-model="form.accountId"
      /></el-form-item>
      <el-form-item
        label="币种"
        prop="currency"
        ><el-input
          v-model="form.currency"
          placeholder="例如 CNY"
          maxlength="3"
      /></el-form-item>
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
        :loading="pending"
        :disabled="!canWrite"
        @click="submit"
        >登记</el-button
      ></template
    >
  </el-dialog>
</template>
