<script setup>
import { useBudgetPeriodEditor } from '@/composables/studio/useBudgetPeriodEditor'
const emit = defineEmits(['saved'])
const { budget, period, open, pending, error, formRef, form, canWrite, start, close, submit } =
  useBudgetPeriodEditor(() => emit('saved'))
defineExpose({ start })
const rules = {
  amount: [
    {
      required: true,
      pattern: /^(0|[1-9]\d{0,13})(\.\d{1,10})?$/,
      message: '额度须为非负十进制数，最多14位整数和10位小数',
      trigger: 'blur',
    },
  ],
  reason: [
    {
      required: true,
      whitespace: true,
      max: 4000,
      message: '请输入原因，最多4000字',
      trigger: 'blur',
    },
  ],
  month: [{ required: true, message: '请选择预算月份', trigger: 'change' }],
  start: [{ required: true, message: '请选择开始时刻', trigger: 'change' }],
}
</script>
<template>
  <el-dialog
    :model-value="open"
    :title="period ? '调整周期额度' : '初始化预算周期'"
    width="min(580px, 95vw)"
    :show-close="!pending"
    :close-on-click-modal="!pending"
    :close-on-press-escape="!pending"
    @close="close"
    destroy-on-close
  >
    <template v-if="budget">
      <p>预算 {{ budget.id }} · {{ budget.currency }} · 业务时区 {{ budget.businessTimezone }}</p>
      <p v-if="period">填写调整后的总额度，已有消费和预占保持不变，降额后可用余额可能为负。</p>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        :disabled="pending"
      >
        <template v-if="!period">
          <el-form-item
            v-if="budget.cycleKind === 'monthly'"
            label="预算月份（按业务时区）"
            prop="month"
            ><el-date-picker
              v-model="form.month"
              type="month"
              value-format="YYYY-MM"
          /></el-form-item>
          <el-form-item
            v-else
            label="开始时刻（按业务时区，无结束时间）"
            prop="start"
            ><el-date-picker
              v-model="form.start"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
          /></el-form-item>
        </template>
        <el-form-item
          :label="period ? '调整后的总额度' : '初始额度'"
          prop="amount"
          ><el-input v-model="form.amount"
        /></el-form-item>
        <el-form-item
          label="原因"
          prop="reason"
          ><el-input
            v-model="form.reason"
            type="textarea"
            :maxlength="4000"
            show-word-limit
        /></el-form-item>
      </el-form>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      />
    </template>
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
        >保存</el-button
      ></template
    >
  </el-dialog>
</template>
