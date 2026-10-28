<script setup>
import { useReconciliationCreate } from '@/composables/studio/useReconciliationCreate'
import { reconciliationInput } from '@/utils/reconciliationInput'
const emit = defineEmits(['saved'])
const { allowed, open, pending, error, formRef, receipt, fileName, stage, progress, form, start, close, selectFile, submit } =
  useReconciliationCreate(() => emit('saved'))
defineExpose({ start })
const rules = {
  accountId: [{ required: true, pattern: /^[1-9]\d{0,18}$/, message: '请输入供应商账号ID', trigger: 'blur' }],
  period: [{ validator: (_rule, _value, callback) => {
    try { reconciliationInput(form); callback() } catch (cause) { callback(cause) }
  }, trigger: 'change' }],
}
</script>

<template>
  <el-dialog :model-value="open" title="导入供应商账单" width="min(720px, 95vw)"
    :show-close="!pending" :close-on-click-modal="!pending" :close-on-press-escape="!pending" @close="close">
    <p>使用 UTF-8 CSV 或单工作表 XLSX，表头为 externalLineKey,currency,amount。XLSX 三列均须使用文本单元格，不接受公式或数值单元格；金额使用十进制文本，保留供应商稳定账单项标识。</p>
    <el-form ref="formRef" :model="form" :rules="rules" :disabled="pending || !!receipt || !allowed" label-position="top">
      <el-form-item label="供应商账号ID" prop="accountId"><el-input v-model="form.accountId" maxlength="19" /></el-form-item>
      <el-form-item label="账期（上海时间，含起点、不含终点）" prop="period">
        <el-date-picker v-model="form.period" type="datetimerange" value-format="YYYY-MM-DD HH:mm:ss" start-placeholder="账期起点" end-placeholder="账期终点" style="width: 100%" />
      </el-form-item>
      <el-form-item label="账单文件">
        <input type="file" accept=".csv,.xlsx" aria-label="选择对账 CSV 或 XLSX 文件" :disabled="pending || !!receipt || !allowed"
          @change="selectFile($event.target.files?.[0]); $event.target.value = ''" />
      </el-form-item>
    </el-form>
    <p v-if="fileName">{{ fileName }} · {{ stage || '待上传' }}</p>
    <el-progress v-if="stage" :percentage="progress" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="receipt" :title="`批次 ${receipt.id} 已受理，等待处理器解析；尚未匹配或确认费用。`" type="success" :closable="false" />
    <p>单文件最大 64 MiB。失败后保留当前文件重试可继续上传；刷新页面不会保留上传状态。</p>
    <template #footer><el-button :disabled="pending" @click="close">{{ receipt ? '完成' : '取消' }}</el-button>
      <el-button v-if="!receipt" type="primary" :disabled="!allowed" :loading="pending" @click="submit">上传并受理</el-button></template>
  </el-dialog>
</template>
