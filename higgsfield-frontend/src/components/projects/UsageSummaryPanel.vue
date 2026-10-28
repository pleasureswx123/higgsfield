<script setup lang="ts">
import { ElDatePicker, ElForm, ElFormItem, ElOption, ElSelect } from 'element-plus'

import type { FormRules } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useUsageSummary } from '@/composables/useUsageSummary'
import { formatBillingDecimal } from '@/utils/billing'
import { usageWindow } from '@/utils/usage'
const props = withDefaults(defineProps<{ projectId?: string; active?: boolean }>(), {
  projectId: undefined,
  active: true,
})
const { formRef, filters, summary, loading, error, search } = useUsageSummary(
  () => props.projectId,
  () => props.active,
)
const rules: FormRules = {
  dates: [
    {
      validator: (_rule, value, callback) => {
        try {
          usageWindow(value || [])
          callback()
        } catch (cause) {
          callback(cause instanceof Error ? cause : new Error('日期无效'))
        }
      },
      trigger: 'change',
    },
  ],
  groupBy: [{ required: true, message: '请选择汇总维度', trigger: 'change' }],
}
const completeness = { available: '完整', partial: '部分已知', unknown: '待确认' }
const groups = [
  { value: 'project', label: '项目' },
  { value: 'model', label: '模型' },
  { value: 'day', label: '日期' },
  { value: 'department', label: '任务归属部门' },
]
</script>

<template>
  <div class="usage-summary">
    <ElForm
      ref="formRef"
      :model="filters"
      :rules="rules"
      label-position="top"
      class="usage-filters"
    >
      <ElFormItem label="日期范围（上海时间，包含结束日）" prop="dates">
        <ElDatePicker
          v-model="filters.dates"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
        />
      </ElFormItem>
      <ElFormItem label="汇总维度" prop="groupBy">
        <ElSelect v-model="filters.groupBy">
          <ElOption
            v-for="group in groups"
            :key="group.value"
            :value="group.value"
            :label="group.label"
          />
        </ElSelect>
      </ElFormItem>
      <Button :disabled="loading" @click="search">{{ loading ? '查询中…' : '查询' }}</Button>
    </ElForm>
    <p class="muted">
      按费用记录创建时间统计{{
        projectId ? '当前项目权限范围内' : '本人当前有权查看'
      }}的平台费用，各币种独立展示。已知合计包含争议金额；尚未形成费用记录的任务不在汇总内。
    </p>
    <p v-if="error" role="alert" class="project-error">{{ error }}</p>
    <p v-else-if="loading" role="status" class="muted">正在读取用量…</p>
    <template v-else-if="summary">
      <p v-if="!summary.rows.length" class="muted">
        当前范围没有费用记录，不能据此判断所有任务均为免费。
      </p>
      <div v-else class="usage-table" tabindex="0" aria-label="用量汇总，可横向滚动">
        <table>
          <thead>
            <tr>
              <th>分组</th>
              <th>币种</th>
              <th>已计算</th>
              <th>已确认</th>
              <th>争议金额</th>
              <th>已知合计</th>
              <th>待确认笔数</th>
              <th>已知输入 Token</th>
              <th>已知输出 Token</th>
              <th>已知视频 Token</th>
              <th>用量完整性</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in summary.rows" :key="JSON.stringify([row.groupKey, row.currency])">
              <th scope="row">{{ row.displayName }}</th>
              <td>{{ row.currency }}</td>
              <td>{{ formatBillingDecimal(row.calculatedAmount) }}</td>
              <td>{{ formatBillingDecimal(row.confirmedAmount) }}</td>
              <td>{{ formatBillingDecimal(row.disputedAmount) }}</td>
              <td>{{ formatBillingDecimal(row.totalKnownAmount) }}</td>
              <td>{{ row.unknownCount }}</td>
              <td>{{ row.usageCompleteness === 'unknown' ? '待确认' : row.inputTokens }}</td>
              <td>{{ row.usageCompleteness === 'unknown' ? '待确认' : row.outputTokens }}</td>
              <td>{{ row.usageCompleteness === 'unknown' ? '待确认' : row.videoTokens }}</td>
              <td>{{ completeness[row.usageCompleteness] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.usage-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}
.usage-filters :deep(.el-select) {
  min-width: 180px;
}
.usage-table {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 12px;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  font-variant-numeric: tabular-nums;
}
th,
td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
thead {
  color: var(--muted-foreground);
}
tbody tr:last-child > * {
  border-bottom: 0;
}
</style>
