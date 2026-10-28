<script setup>
import { useModelVersionEditor } from '@/composables/studio/useModelVersionEditor'
import { parseCapabilities } from '@/utils/modelCapabilities'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, error, model, editing, formRef, form, start, close, submit } =
  useModelVersionEditor(() => emit('saved'))
defineExpose({ start })
const rules = {
  gatewayAlias: [
    {
      required: true,
      pattern: /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}$/,
      message: '请输入100字符以内的有效网关别名',
      trigger: 'blur',
    },
  ],
  underlyingModelId: [{ max: 255, message: '底层模型标识最多255字符', trigger: 'blur' }],
  region: [
    {
      required: true,
      pattern: /^[a-z][a-z0-9_-]{0,31}$/,
      message: '区域以小写字母开头，最多32字符',
      trigger: 'blur',
    },
  ],
  capabilities: [
    {
      validator: (_rule, value, callback) => {
        try {
          parseCapabilities(value)
          callback()
        } catch (cause) {
          callback(cause instanceof Error ? cause : new Error('能力配置无效'))
        }
      },
      trigger: 'blur',
    },
  ],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    :title="editing ? '编辑草稿能力版本' : '新增草稿能力版本'"
    width="min(900px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    @close="close"
    destroy-on-close
  >
    <p v-if="model">{{ model.displayName }} · {{ model.code }}</p>
    <p>
      保存仅生成或修改草稿，不代表已验证或发布。已有精确规格必须与更新后的能力维度兼容，服务端会完整校验配置。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      :disabled="pending"
    >
      <el-form-item
        label="供应商网关别名"
        prop="gatewayAlias"
        ><el-input
          v-model="form.gatewayAlias"
          maxlength="100"
      /></el-form-item>
      <el-form-item
        label="底层模型标识（可留空）"
        prop="underlyingModelId"
        ><el-input
          v-model="form.underlyingModelId"
          maxlength="255"
      /></el-form-item>
      <el-form-item
        v-if="!editing"
        label="区域"
        prop="region"
        ><el-input
          v-model="form.region"
          maxlength="32"
      /></el-form-item>
      <p v-else>区域：{{ editing.region }}（修改区域须新增版本）</p>
      <el-form-item
        label="完整能力配置（JSON）"
        prop="capabilities"
        ><el-input
          v-model="form.capabilities"
          type="textarea"
          :rows="20"
          spellcheck="false"
      /></el-form-item>
      <p>
        配置包括计价维度 variantDimensions、参数 parametersSchema、引用 referenceRules、默认参数
        defaultParameters、展示信息 presentation 和估价策略
        estimatePolicy。不得填入凭据、脚本或未核实能力；未配置估价策略不表示免费。
      </p>
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
        >保存草稿版本</el-button
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
