<script setup>
defineProps({ row: { type: Object, required: true } })
const labels = {
  sourceCurrency: '原币种', targetCurrency: '预算币种', sourceAmount: '累计原币金额',
  rate: '固定汇率', rawAmount: '未舍入换算金额', amount: '换算金额',
  calculationScale: '小数位数', at: '汇率适用时点', sourceAdjustmentAmount: '本次原币调整',
  previousConvertedAmount: '调整前累计换算金额', convertedDelta: '本次预算记账差额',
}
</script>
<template>
  <div class="evidence">
    <el-descriptions :column="2" border>
      <el-descriptions-item label="预占ID">{{ row.reservationId || '—' }}</el-descriptions-item>
      <el-descriptions-item label="费用事件ID">{{ row.billingEventId || '—' }}</el-descriptions-item>
      <el-descriptions-item label="调整ID">{{ row.adjustmentId || '—' }}</el-descriptions-item>
      <el-descriptions-item label="固定汇率版本ID">{{ row.exchangeRateVersionId || '未使用汇率' }}</el-descriptions-item>
      <template v-if="row.conversion">
        <el-descriptions-item v-for="(label, key) in labels" :key="key" :label="label">
          {{ row.conversion[key] ?? '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="换算方向">{{ row.conversion.direction === 'multiply' ? '乘以汇率' : row.conversion.direction === 'divide' ? '除以汇率' : '—' }}</el-descriptions-item>
        <el-descriptions-item label="舍入方式">{{ row.conversion.roundingMode === 'ceiling' ? '向上舍入（预占）' : row.conversion.roundingMode === 'half_up' ? '四舍五入' : '—' }}</el-descriptions-item>
      </template>
    </el-descriptions>
    <p v-if="row.conversion">费用调整按累计换算金额的差额记账；原币金额、固定汇率及原始费用不会被覆盖。</p>
  </div>
</template>
<style scoped>
.evidence { padding: 16px; color: var(--el-text-color-regular); }
p { color: var(--el-text-color-secondary); }
:deep(.el-descriptions__content) { overflow-wrap: anywhere; }
</style>
