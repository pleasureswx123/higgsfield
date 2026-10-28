<script setup lang="ts">
import type { GenerationSummary } from '@/api/generations'
import { formatBillingDecimal } from '@/utils/billing'
defineProps<{ task: GenerationSummary }>()
const states = { pending: '待确认', calculated: '已计算', confirmed: '已确认', disputed: '有争议' }
</script>
<template>
  <span v-if="task.billingVisibility === 'hidden'">无费用查看权限</span>
  <span v-else-if="task.billingVisibility === 'visible' && task.billingSummary">
    {{ formatBillingDecimal(task.billingSummary.amount) }}<template v-if="task.billingSummary.amount !== null"> {{ task.billingSummary.currency }}</template>
    · {{ states[task.billingSummary.state] }}
  </span>
  <span v-else>费用摘要暂不可用</span>
</template>
