<script setup>
import { usePriceActivationEnd } from '@/composables/studio/usePriceActivationEnd'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, uncertain, error, version, formRef, form, start, close, submit } =
  usePriceActivationEnd(() => emit('saved'))
defineExpose({ start })
const rules = {
  effectiveUntil: [{ required: true, message: '请选择结束时间', trigger: 'change' }],
  reason: [{ required: true, whitespace: true, message: '请填写结束原因', trigger: 'blur' }],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    title="结束价格生效区间"
    width="min(680px, 95vw)"
    :show-close="!pending && !uncertain"
    :close-on-click-modal="!pending && !uncertain"
    :close-on-press-escape="!pending && !uncertain"
    destroy-on-close
    @close="close"
  >
    <p>
      区间 {{ version?.id }} · 修订
      {{ version?.revision }}。此操作只缩短生效区间，保留价格正文和历史。
    </p>
    <p>
      历史快照：{{ version?.effectiveFrom }} 至
      {{
        version?.effectiveUntil || '无结束时间'
      }}。历史可能已过期；发生版本冲突时请刷新历史，选择最新修订记录。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="pending || uncertain"
      label-position="top"
    >
      <el-form-item
        label="新的结束时间（上海时间）"
        prop="effectiveUntil"
        ><el-date-picker
          v-model="form.effectiveUntil"
          type="datetime"
          value-format="YYYY-MM-DD HH:mm:ss"
      /></el-form-item>
      <el-form-item
        label="结束原因"
        prop="reason"
        ><el-input
          v-model="form.reason"
          type="textarea"
          maxlength="4000"
      /></el-form-item>
    </el-form>
    <el-alert v-if="uncertain" title="原请求结果尚未确认。请用原请求重试确认，暂不能修改内容或关闭。" type="warning" :closable="false" />
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    />
    <template #footer
      ><el-button
        :disabled="pending || uncertain"
        @click="close"
        >取消</el-button
      ><el-button
        type="primary"
        :loading="pending"
        :disabled="!canWrite"
        @click="submit"
        >结束区间</el-button
      ></template
    >
  </el-dialog>
</template>
