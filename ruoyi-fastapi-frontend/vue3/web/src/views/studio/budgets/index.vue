<script setup>
import { computed, ref } from 'vue'
import useUserStore from '@/store/modules/user'
import BudgetEditor from './BudgetEditor.vue'
import BudgetPeriodEditor from './BudgetPeriodEditor.vue'
import BudgetLedgerEvidence from './BudgetLedgerEvidence.vue'
import { useBudgets } from '@/composables/studio/useBudgets'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const user = useUserStore()
const canWrite = computed(
  () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:budget')
)
const editor = ref()
const periodEditor = ref()
const {
  filters,
  formRef,
  budgets,
  periods,
  ledger,
  budget,
  period,
  canReadLedger,
  search,
  load,
  loadPeriods,
  selectBudget,
  loadLedger,
  selectPeriod,
} = useBudgets()
const rules = {
  subjectId: [
    {
      validator: (_rule, value, callback) =>
        callback(
          !value || (filters.subjectType && /^[1-9]\d{0,18}$/.test(value))
            ? undefined
            : new Error('按主体ID筛选时请选择主体类型并输入有效ID')
        ),
      trigger: 'blur',
    },
  ],
}
const purposes = { platform: '平台', procurement: '采购' }
const entries = {
  reserve: '预占',
  release: '释放预占',
  settle: '结算',
  adjust: '调整',
  change_limit: '额度变动',
}
</script>
<template>
  <div class="app-container">
    <BudgetPeriodEditor
      ref="periodEditor"
      @saved="loadPeriods"
    />
    <BudgetEditor
      ref="editor"
      @saved="load"
    />
    <div class="heading">
      <h2>预算管理</h2>
      <el-button
        v-if="canWrite"
        type="primary"
        @click="editor.start()"
        >创建预算</el-button
      >
      <el-button @click="settings.toggleTheme()">{{
        settings.isDark ? '切换亮色' : '切换暗色'
      }}</el-button>
    </div>
    <el-form
      ref="formRef"
      :model="filters"
      :rules="rules"
      inline
      label-position="top"
    >
      <el-form-item label="主体类型"
        ><el-select
          v-model="filters.subjectType"
          clearable
          ><el-option
            label="项目"
            value="project" /><el-option
            label="用户"
            value="user" /></el-select
      ></el-form-item>
      <el-form-item
        label="主体ID"
        prop="subjectId"
        ><el-input
          v-model="filters.subjectId"
          clearable
      /></el-form-item>
      <el-form-item label="口径"
        ><el-select
          v-model="filters.purpose"
          clearable
          ><el-option
            label="平台"
            value="platform" /><el-option
            label="采购"
            value="procurement" /></el-select
      ></el-form-item>
      <el-form-item label="操作"
        ><el-button
          type="primary"
          :loading="budgets.loading"
          @click="search"
          >查询</el-button
        ></el-form-item
      >
    </el-form>
    <el-alert
      v-if="budgets.error"
      :title="budgets.error"
      type="error"
      :closable="false"
    />
    <el-table
      v-loading="budgets.loading"
      :data="budgets.rows"
      empty-text="当前范围没有预算"
    >
      <el-table-column
        prop="id"
        label="预算ID"
      /><el-table-column label="主体"
        ><template #default="{ row }">{{
          row.subject.projectId ? `项目 ${row.subject.projectId}` : `用户 ${row.subject.userId}`
        }}</template></el-table-column
      >
      <el-table-column label="口径"
        ><template #default="{ row }">{{ purposes[row.purpose] }}</template></el-table-column
      ><el-table-column
        prop="currency"
        label="币种"
      />
      <el-table-column label="周期类型"
        ><template #default="{ row }">{{
          row.cycleKind === 'monthly' ? '月度' : '总额'
        }}</template></el-table-column
      ><el-table-column
        prop="businessTimezone"
        label="业务时区"
      />
      <el-table-column label="状态"
        ><template #default="{ row }">{{ row.active ? '启用' : '停用' }}</template></el-table-column
      >
      <el-table-column label="操作"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            @click="selectBudget(row)"
            >查看周期</el-button
          >
          <el-button
            v-if="canWrite"
            link
            type="primary"
            @click="editor.start(row)"
            >{{ row.active ? '停用' : '启用' }}</el-button
          >
        </template></el-table-column
      >
    </el-table>
    <el-pagination
      v-if="budgets.total"
      v-model:current-page="budgets.page"
      :page-size="20"
      :total="budgets.total"
      layout="total, prev, pager, next"
      @current-change="load"
    />
    <section v-if="budget">
      <h3>预算 {{ budget.id }} 的周期 · {{ purposes[budget.purpose] }} · {{ budget.currency }}</h3>
      <el-button
        v-if="canWrite"
        type="primary"
        @click="periodEditor.start(budget)"
        >初始化周期</el-button
      >
      <p class="hint">停用预算不会释放已有预占。可用额允许为负，表示实际消费已超出额度。</p>
      <el-alert
        v-if="periods.error"
        :title="periods.error"
        type="error"
        :closable="false"
      />
      <el-table
        v-loading="periods.loading"
        :data="periods.rows"
        empty-text="尚无预算周期"
      >
        <el-table-column
          prop="periodStart"
          label="开始时刻"
          min-width="200"
        /><el-table-column
          label="结束时刻"
          min-width="200"
          ><template #default="{ row }">{{
            row.periodEnd || '无结束时间'
          }}</template></el-table-column
        >
        <el-table-column
          v-for="(label, field) in {
            limitAmount: '额度',
            reservedAmount: '预占',
            consumedAmount: '已消费',
            availableAmount: '可用',
          }"
          :key="field"
          :prop="field"
          :label="label"
          min-width="160"
        />
        <el-table-column
          v-if="canReadLedger || canWrite"
          label="操作"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              @click="selectPeriod(row)"
              v-if="canReadLedger"
              >查看账本</el-button
            >
            <el-button
              v-if="canWrite"
              link
              type="primary"
              @click="periodEditor.start(budget, row)"
              >调整额度</el-button
            >
          </template></el-table-column
        >
      </el-table>
      <el-pagination
        v-if="periods.total"
        v-model:current-page="periods.page"
        :page-size="20"
        :total="periods.total"
        layout="total, prev, pager, next"
        @current-change="loadPeriods"
      />
    </section>
    <section v-if="period && canReadLedger">
      <h3>周期 {{ period.id }} 的不可变账本 · {{ budget.currency }}</h3>
      <el-alert
        v-if="ledger.error"
        :title="ledger.error"
        type="error"
        :closable="false"
      />
      <el-table
        v-loading="ledger.loading"
        :data="ledger.rows"
        row-key="id"
        empty-text="暂无账本记录"
      >
        <el-table-column type="expand" label="依据"><template #default="{ row }"><BudgetLedgerEvidence :row="row" /></template></el-table-column>
        <el-table-column
          prop="id"
          label="流水ID"
        /><el-table-column label="类型"
          ><template #default="{ row }">{{
            entries[row.entryType] || row.entryType
          }}</template></el-table-column
        >
        <el-table-column
          v-for="(label, field) in {
            limitDelta: '额度变化',
            reservedDelta: '预占变化',
            consumedDelta: '消费变化',
            reason: '原因',
            createTime: '时间',
          }"
          :key="field"
          :prop="field"
          :label="label"
          min-width="160"
        />
      </el-table>
      <el-pagination
        v-if="ledger.total"
        v-model:current-page="ledger.page"
        :page-size="20"
        :total="ledger.total"
        layout="total, prev, pager, next"
        @current-change="loadLedger"
      />
    </section>
  </div>
</template>
<style scoped>
.heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.el-select,
.el-input {
  width: 180px;
}
.el-pagination,
section {
  margin-top: 20px;
}
.hint {
  color: var(--el-text-color-secondary);
}
</style>
