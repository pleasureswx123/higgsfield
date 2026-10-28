<script setup>
import { usePricePublish } from '@/composables/studio/usePricePublish'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, uncertain, error, version, formRef, form, start, close, submit } =
  usePricePublish(() => emit('saved'))
defineExpose({ start })
const rules = {
  effectiveFrom: [{ required: true, message: '请选择生效起点', trigger: 'change' }],
  reason: [{ required: true, whitespace: true, message: '请填写发布原因', trigger: 'blur' }],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    title="发布价格与生效区间"
    width="min(680px, 95vw)"
    :show-close="!pending && !uncertain"
    :close-on-click-modal="!pending && !uncertain"
    :close-on-press-escape="!pending && !uncertain"
    destroy-on-close
    @close="close"
  >
    <p>
      价格版本 {{ version?.id }} · 修订
      {{
        version?.revision
      }}。发布后正文不可修改。生效时间使用上海时间，区间左闭右开；留空结束时间表示持续生效。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="pending || uncertain"
      label-position="top"
    >
      <el-form-item
        label="生效起点（上海时间）"
        prop="effectiveFrom"
        ><el-date-picker
          v-model="form.effectiveFrom"
          type="datetime"
          value-format="YYYY-MM-DD HH:mm:ss"
      /></el-form-item>
      <el-form-item label="结束时间（可选，上海时间）"
        ><el-date-picker
          v-model="form.effectiveUntil"
          type="datetime"
          value-format="YYYY-MM-DD HH:mm:ss"
      /></el-form-item>
      <el-form-item
        label="发布原因"
        prop="reason"
        ><el-input
          v-model="form.reason"
          type="textarea"
          maxlength="4000"
      /></el-form-item>
      <details>
        <summary>替换已有生效区间（可选）</summary>
        <p>
          从历史记录核对区间ID与最新修订号。替换会将旧区间结束时间缩短到新起点，服务端校验区间归属、版本与重叠。
        </p>
        <el-form-item label="旧生效区间ID"
          ><el-input v-model="form.replaceActivationId"
        /></el-form-item>
        <el-form-item label="旧区间预期修订号"
          ><el-input v-model="form.expectedActivationRevision"
        /></el-form-item>
      </details>
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
        >发布价格</el-button
      ></template
    >
  </el-dialog>
</template>
