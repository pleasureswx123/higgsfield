<script setup>
import { watch } from 'vue'
import { useBillingAdjustment } from '@/composables/studio/useBillingAdjustment'
const props = defineProps({ event: { type: Object, required: true } })
const emit = defineEmits(['saved', 'pending'])
const { canAdjust, form, formRef, pending, uncertain, error, submit } = useBillingAdjustment(
  () => props.event,
  () => emit('saved')
)
watch(() => pending.value || uncertain.value, (value) => emit('pending', value), { flush: 'sync' })
const rules = {
  reconciliationLineId: [{ validator: (_rule, value, callback) => {
    const text = value.trim()
    callback(!text || (/^[1-9]\d{0,18}$/.test(text) && BigInt(text) <= 9223372036854775807n)
      ? undefined : new Error('请输入有效的账单明细ID'))
  }, trigger: 'blur' }],
  deltaAmount: [
    {
      validator: (_rule, value, callback) =>
        callback(
          /^-?(0|[1-9]\d{0,13})(\.\d{1,10})?$/.test(value) && /[1-9]/.test(value)
            ? undefined
            : new Error('请输入非零调整金额，最多14位整数和10位小数，不使用科学计数法')
        ),
      trigger: 'blur',
    },
  ],
  reason: [
    {
      required: true,
      whitespace: true,
      min: 1,
      max: 500,
      message: '请输入调整原因（最多500字）',
      trigger: 'blur',
    },
  ],
}
</script>
<template>
  <section v-if="canAdjust">
    <h3>追加费用调整</h3>
    <p v-if="event.amount === null">原始金额尚未确认，暂不能调整。</p>
    <template v-else>
      <p>
        正数增加费用，负数减少费用，币种为
        {{ event.currency }}。提交后保留原始记录{{ event.jobId ? '，并同步原预算周期' : '，调整计入原成本中心' }}。
      </p>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        :disabled="pending"
      >
        <el-form-item
          label="调整金额"
          prop="deltaAmount"
          ><el-input
            :disabled="pending || uncertain"
            v-model="form.deltaAmount"
            placeholder="例如 -0.01"
        /></el-form-item>
        <el-form-item
          label="调整原因"
          prop="reason"
          ><el-input
            :disabled="pending || uncertain"
            v-model="form.reason"
            type="textarea"
            :maxlength="500"
            show-word-limit
        /></el-form-item>
        <el-form-item label="对账依据（可选）" prop="reconciliationLineId">
          <el-input :disabled="pending || uncertain"
            v-model="form.reconciliationLineId" placeholder="同账号、同计费对象、同币种的已确认账单明细ID" />
        </el-form-item>
        <el-alert v-if="uncertain" title="调整结果未确认，请使用原请求重试确认，暂不能修改金额或关闭。" type="warning" :closable="false" />
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          :closable="false"
        />
        <el-button
          type="primary"
          :loading="pending"
          @click="submit"
          >{{ uncertain ? '重试确认原调整' : '提交调整' }}</el-button
        >
      </el-form>
    </template>
  </section>
</template>
<style scoped>
p {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.el-alert {
  margin-bottom: 12px;
}
</style>
