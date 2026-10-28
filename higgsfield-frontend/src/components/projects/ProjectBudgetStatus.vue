<script setup lang="ts">
import Button from '@/components/ui/Button.vue'
import { useBudgetStatus } from '@/composables/useBudgetStatus'
import { formatBudgetDecimal } from '@/utils/billing'
const props = defineProps<{ projectId: string; refreshKey?: string }>()
const { status, loading, error, refresh } = useBudgetStatus(
  () => props.projectId,
  () => props.refreshKey,
)
const reasons: Record<string, string> = {
  PROJECT_READ_ONLY: '项目当前不可提交生成',
  GENERATION_PERMISSION_REQUIRED: '当前没有生成权限',
  BUDGET_REQUIRED: '尚未配置适用预算',
  BUDGET_PERIOD_REQUIRED: '预算缺少当前周期',
  BUDGET_PERIOD_AMBIGUOUS: '预算周期重叠，请联系管理员',
  BUDGET_INSUFFICIENT: '至少一项适用预算额度不足',
  BUDGET_ESTIMATE_REQUIRED: '预算币种缺少对应估价配置',
}
</script>

<template>
  <section class="project-budget" aria-label="当前预算状态">
    <div class="budget-heading">
      <h3>预算状态</h3>
      <Button variant="ghost" :disabled="loading" @click="refresh">刷新</Button>
    </div>
    <p v-if="loading" class="muted" role="status">正在读取预算…</p>
    <p v-else-if="error" class="project-error" role="alert">{{ error }}</p>
    <template v-else-if="status">
      <p v-if="status.canSubmit" class="muted">当前预算检查通过，生成前仍需按所选模型预检。</p>
      <ul v-else>
        <li v-for="code in status.blockingCodes" :key="code">
          {{ reasons[code] || '预算检查未通过，请联系管理员' }}
        </li>
      </ul>
      <p v-if="status.amountVisibility === 'hidden'" class="muted">当前没有预算金额查看权限。</p>
      <template v-else-if="status.amountVisibility === 'visible'">
        <dl v-for="period in status.periods || []" :key="period.id">
          <dt>平台预算 · {{ period.currency }}</dt>
          <dd>
            可用 {{ formatBudgetDecimal(period.availableAmount) }} · 已消费
            {{ formatBudgetDecimal(period.consumedAmount) }} · 预占
            {{ formatBudgetDecimal(period.reservedAmount) }}
          </dd>
        </dl>
      </template>
    </template>
  </section>
</template>

<style scoped>
.project-budget {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin: 12px 0;
  background: var(--surface);
}
.budget-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
h3 {
  margin: 0;
}
dl {
  margin: 12px 0 0;
}
dd {
  margin: 6px 0 0;
  overflow-wrap: anywhere;
  font-variant-numeric: tabular-nums;
}
</style>
