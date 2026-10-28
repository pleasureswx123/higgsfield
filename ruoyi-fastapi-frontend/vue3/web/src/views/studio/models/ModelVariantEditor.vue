<script setup>
import { useModelVariantEditor } from '@/composables/studio/useModelVariantEditor'
import { parseVariantDimension } from '@/utils/modelVariant'
const props = defineProps({ version: { type: Object, required: true } })
const emit = defineEmits(['saved'])
const { canWrite, open, pending, error, selected, formRef, form, start, close, submit } =
  useModelVariantEditor(
    () => props.version,
    () => emit('saved')
  )
function rules(rule) {
  return [
    {
      validator: (_rule, value, callback) => {
        try {
          parseVariantDimension(rule, value)
          callback()
        } catch (cause) {
          callback(cause instanceof Error ? cause : new Error('规格值无效'))
        }
      },
      trigger: 'change',
    },
  ]
}
</script>
<template>
  <el-button
    v-if="canWrite"
    @click="start"
    >登记精确规格</el-button
  >
  <el-dialog
    :model-value="open"
    title="登记精确规格"
    width="min(640px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    @close="close"
    destroy-on-close
  >
    <p>填写当前能力版本的全部计价维度。已登记规格不可覆盖，服务端会重新校验草稿状态与维度规则。</p>
    <el-form
      v-if="selected"
      ref="formRef"
      :model="form"
      label-position="top"
      :disabled="pending"
    >
      <p v-if="!Object.keys(selected.capabilities.variantDimensions).length">
        此版本未声明维度，将登记一项无维度规格。
      </p>
      <el-form-item
        v-for="(rule, name) in selected.capabilities.variantDimensions"
        :key="name"
        :label="rule.title || name"
        :prop="[name]"
        :rules="rules(rule)"
      >
        <el-select
          v-if="rule.enum != null"
          v-model="form[name]"
          ><el-option
            v-for="value in rule.enum"
            :key="JSON.stringify(value)"
            :value="JSON.stringify(value)"
            :label="String(value)"
        /></el-select>
        <el-select
          v-else-if="rule.type === 'boolean'"
          v-model="form[name]"
          ><el-option
            label="是"
            value="true" /><el-option
            label="否"
            value="false"
        /></el-select>
        <el-input
          v-else
          v-model="form[name]"
          :placeholder="rule.type === 'string' ? '字符串' : '数字'"
        />
        <span
          v-if="rule.description"
          class="hint"
          >{{ rule.description }}</span
        >
      </el-form-item>
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
        >登记规格</el-button
      ></template
    >
  </el-dialog>
</template>
<style scoped>
.hint,
p {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.hint {
  display: block;
  width: 100%;
}
.el-select {
  width: 100%;
}
</style>
