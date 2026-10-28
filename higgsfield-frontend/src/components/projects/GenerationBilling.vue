<script setup lang="ts">
import type { GenerationSnapshot } from '@/api/generations'
import { formatBillingDecimal } from '@/utils/billing'

defineProps<{ detail: GenerationSnapshot }>()
const states = { pending: '待确认', calculated: '已计算', confirmed: '已确认', disputed: '有争议' }
const completeness = {
  unknown: '用量待确认',
  partial: '用量不完整或修订待核查',
  available: '用量已记录',
}
</script>

<template>
  <section class="generation-billing" aria-label="平台费用与用量">
    <h3>平台费用</h3>
    <p v-if="detail.billingVisibility === 'hidden'" class="muted">当前没有费用查看权限。</p>
    <p v-else-if="detail.billingVisibility !== 'visible' || !detail.billing" class="muted">
      费用明细暂不可用，不能据此判断为免费。
    </p>
    <template v-else>
      <p class="billing-amount">
        {{ formatBillingDecimal(detail.billing.platform.amount) }}
        <span v-if="detail.billing.platform.amount !== null">{{
          detail.billing.platform.currency
        }}</span>
        <span class="muted"> · {{ states[detail.billing.platform.state] }}</span>
      </p>
      <p class="muted">{{ completeness[detail.usageState] }}</p>
      <dl v-for="subject in detail.billing.usage.subjects" :key="subject.subjectId">
        <div>
          <dt>计费对象</dt>
          <dd>{{ subject.subjectId }}</dd>
        </div>
        <div v-if="subject.inputTokens !== null">
          <dt>输入 Token</dt>
          <dd>{{ subject.inputTokens }}</dd>
        </div>
        <div v-if="subject.outputTokens !== null">
          <dt>输出 Token</dt>
          <dd>{{ subject.outputTokens }}</dd>
        </div>
        <div v-if="subject.videoTokens !== null">
          <dt>视频 Token</dt>
          <dd>{{ subject.videoTokens }}</dd>
        </div>
        <div v-if="subject.imageCount !== null">
          <dt>计费图片数</dt>
          <dd>{{ subject.imageCount }}</dd>
        </div>
        <div v-if="subject.outputSeconds !== null">
          <dt>输出时长</dt>
          <dd>{{ formatBillingDecimal(subject.outputSeconds) }} 秒</dd>
        </div>
        <div v-if="subject.referenceSeconds !== null">
          <dt>参考时长</dt>
          <dd>{{ formatBillingDecimal(subject.referenceSeconds) }} 秒</dd>
        </div>
      </dl>
      <p v-if="detail.billing.platform.state === 'disputed'" class="muted">
        费用存在争议，请等待核查。
      </p>
    </template>
  </section>
</template>

<style scoped>
.generation-billing {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin: 12px 0;
  background: var(--surface);
}
h3 {
  margin: 0 0 12px;
}
.billing-amount {
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
dl {
  margin: 12px 0;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
dl > div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin: 6px 0;
}
dt {
  color: var(--muted-foreground);
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
  text-align: right;
}
</style>
