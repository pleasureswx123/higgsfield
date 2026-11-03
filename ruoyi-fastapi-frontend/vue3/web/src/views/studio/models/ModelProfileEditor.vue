<script setup>
import { useModelProfileEditor } from '@/composables/studio/useModelProfileEditor'
import { videoModels } from '@/utils/videoModels'
defineProps({ supplierName: { type: String, default: '' } })
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
    title="新增模型"
    width="min(580px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    @close="close"
    destroy-on-close
  >
    <p>
      模型使用当前供应商的连接与密钥。保存后返回列表继续配置；仅登记不会生成图片、视频或产生供应商费用。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      :disabled="pending"
    >
      <p v-if="supplierName">供应商：{{ supplierName }}。沿用已有密钥，无需重新填写。</p>
      <el-form-item v-if="supplierName" label="选择模型" prop="code">
        <el-select :model-value="form.code || undefined" placeholder="选择要添加的图片或视频模型" @change="code => { const model = videoModels.find(item => item.code === code); Object.assign(form, { code, displayName: model?.alias || 'mm-imagen2', kind: model ? 'video' : 'image' }) }">
          <el-option label="mm-imagen2 · 图片生成与编辑" value="mm-imagen2" />
          <el-option v-for="model in videoModels" :key="model.alias" :label="`${model.name}（${model.alias}）`" :value="model.code" />
        </el-select>
      </el-form-item>
      <p v-if="supplierName">下一步确认价格、手动测试并启用。保存模型不会自动发起付费生成，已有图片模型保持可用。</p>
      <el-form-item
        v-if="!supplierName"
        label="供应商连接ID"
        prop="connectionId"
        ><el-input v-model="form.connectionId"
      /></el-form-item>
      <el-form-item
        v-if="!supplierName"
        label="模型标识"
        prop="code"
        ><el-input
          v-model="form.code"
          maxlength="100"
          placeholder="例如 image-model-a"
      /></el-form-item>
      <el-form-item
        label="模型名称"
        prop="displayName"
        ><el-input
          v-model="form.displayName"
          maxlength="200"
      /></el-form-item>
      <el-form-item
        v-if="!supplierName"
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
        >保存模型</el-button
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
