<script setup>
import { usePriceSourceEditor } from '@/composables/studio/usePriceSourceEditor'
const emit = defineEmits(['saved'])
const { canWrite, open, pending, error, formRef, form, fileName, uploadStage,
  uploadProgress, selectFile, upload, start, close, submit } =
  usePriceSourceEditor((source) => emit('saved', source))
defineExpose({ start })
const rules = {
  sourceType: [{ required: true, message: '请选择来源类型', trigger: 'change' }],
  excerpt: [
    { required: true, whitespace: true, message: '请填写原文摘录或人工确认依据', trigger: 'blur' },
  ],
  observedAt: [{ required: true, message: '请选择获取时间', trigger: 'change' }],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    title="登记价格来源"
    width="min(700px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    destroy-on-close
    @close="close"
  >
    <p>
      来源登记后不可修改。请核对摘录、出处和实际获取时间；登记不会自动抓取网址、绑定价格版本或发布价格。
    </p>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="pending"
      label-position="top"
    >
      <el-form-item
        label="来源类型"
        prop="sourceType"
        ><el-select v-model="form.sourceType"
          ><el-option
            label="供应商文档"
            value="vendor_document" /><el-option
            label="官方截图出处"
            value="official_screenshot" /><el-option
            label="人工确认"
            value="manual_confirmation" /></el-select
      ></el-form-item>
      <el-form-item
        label="出处地址（与已校验附件至少提供一项，人工确认除外）"
        prop="sourceUrl"
        ><el-input
          v-model="form.sourceUrl"
          maxlength="4000"
          placeholder="https://"
      /></el-form-item>
      <el-form-item label="证据附件（可选）">
        <div>
          <input type="file" accept=".csv,.txt,.xlsx,.png,.jpg,.jpeg,.webp" aria-label="选择价格证据附件"
            :disabled="pending || !canWrite" @change="selectFile($event.target.files?.[0]); $event.target.value = ''" />
          <p>支持 UTF-8 CSV/TXT、XLSX 和 PNG/JPEG/WebP 截图，最大 64 MiB；附件完成校验后随来源永久绑定。</p>
          <template v-if="fileName">
            <p>{{ fileName }} · {{ uploadStage || '待上传' }}</p>
            <el-progress :percentage="uploadProgress" :status="form.uploadId ? 'success' : undefined" />
            <el-button text type="primary" :disabled="pending || !canWrite || !!form.uploadId" @click="upload">上传 / 重试</el-button>
            <el-button text :disabled="pending" @click="selectFile()">移除附件</el-button>
          </template>
        </div>
      </el-form-item>
      <el-form-item
        label="原文摘录或人工确认依据"
        prop="excerpt"
        ><el-input
          v-model="form.excerpt"
          type="textarea"
          :rows="10"
          maxlength="20000"
          show-word-limit
      /></el-form-item>
      <el-form-item
        label="获取时间（上海时间）"
        prop="observedAt"
        ><el-date-picker
          v-model="form.observedAt"
          type="datetime"
          value-format="YYYY-MM-DD HH:mm:ss"
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
        >登记来源</el-button
      ></template
    >
  </el-dialog>
</template>
