<script setup>
defineProps({ summary: { type: Object, default: undefined } })
const states = { available: '完整', partial: '部分已知', unknown: '待确认' }
const columns = [
  ['calculatedAmount', '已计算金额'],
  ['confirmedAmount', '已确认金额'],
  ['disputedAmount', '争议金额'],
  ['totalKnownAmount', '已知合计'],
  ['unknownCount', '待确认笔数'],
]
const tokens = [
  ['inputTokens', '已知输入 Token'],
  ['outputTokens', '已知输出 Token'],
  ['videoTokens', '已知视频 Token'],
]
</script>
<template>
  <section>
    <p class="hint">
      按费用记录创建时间汇总，结束时刻不包含。已知合计包含争议金额；尚未形成费用记录的任务不在汇总内，各币种独立展示。
    </p>
    <el-table
      v-if="summary"
      :data="summary.rows"
      empty-text="当前范围没有费用记录"
    >
      <el-table-column
        prop="displayName"
        label="分组"
        min-width="180"
      />
      <el-table-column
        prop="currency"
        label="币种"
        width="85"
      />
      <el-table-column
        v-for="[field, label] in columns"
        :key="field"
        :prop="field"
        :label="label"
        min-width="160"
      />
      <el-table-column
        v-for="[field, label] in tokens"
        :key="field"
        :label="label"
        min-width="160"
        ><template #default="{ row }">{{
          row.usageCompleteness === 'unknown' ? '待确认' : row[field]
        }}</template></el-table-column
      >
      <el-table-column
        label="用量完整性"
        width="120"
        ><template #default="{ row }">{{
          states[row.usageCompleteness]
        }}</template></el-table-column
      >
    </el-table>
    <p
      v-else
      class="hint"
    >
      请选择时间范围后查询。
    </p>
  </section>
</template>
<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
