<script setup>
import { ref } from 'vue'
import useSettingsStore from '@/store/modules/settings'
import { useBillingEvents } from '@/composables/studio/useBillingEvents'
import BillingAdjustment from './BillingAdjustment.vue'
import BillingSummary from './BillingSummary.vue'
import { billingTimeWindow } from '@/utils/billingQuery'
const settings = useSettingsStore()
const adjustmentPending = ref(false)
function adjustmentSaved() {
  adjustmentPending.value = false
  void load()
}
const {
  allowed,
  filters,
  formRef,
  rows,
  summary,
  total,
  page,
  loading,
  error,
  detail,
  detailOpen,
  detailLoading,
  detailError,
  search,
  load,
  select,
  closeDetail,
} = useBillingEvents()
const states = { pending: '待确认', calculated: '已计算', confirmed: '已确认', disputed: '有争议' }
const usageLabels = {
  inputTokens: '输入 Token',
  outputTokens: '输出 Token',
  videoTokens: '视频 Token',
  imageCount: '图片数量',
  outputSeconds: '输出秒数',
  referenceSeconds: '参考秒数',
}
const rules = {
  timeRange: [
    {
      validator: (_rule, value, callback) => {
        try {
          const window = billingTimeWindow(value)
          if (filters.mode === 'summary' && !window.from)
            throw new Error('汇总查询必须选择起止时间')
          callback()
        } catch (cause) {
          callback(cause instanceof Error ? cause : new Error('时间范围无效'))
        }
      },
      trigger: 'change',
    },
  ],
  userId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效的用户ID', trigger: 'blur' }],
  currency: [{ pattern: /^[A-Z]{3}$/, message: '请输入三位大写币种代码', trigger: 'blur' }],
  projectId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效的项目ID', trigger: 'blur' }],
  jobId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效的任务ID', trigger: 'blur' }],
  costCenterId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效的成本中心ID', trigger: 'blur' }],
}
// 保留十进制字符串，不经浮点数转换；未知金额不能显示为零。
const amount = (value) => (value == null ? '待确认' : String(value))
</script>

<template>
  <div class="app-container billing-console">
    <el-alert v-if="!allowed" title="没有费用读取权限或会话已失效" type="warning" :closable="false" />
    <div class="heading">
      <h2>费用记录</h2>
      <el-button @click="settings.toggleTheme()">{{
        settings.isDark ? '切换亮色' : '切换暗色'
      }}</el-button>
    </div>
    <el-form
      ref="formRef"
      :model="filters"
      :rules="rules"
      :inline="true"
      label-position="top"
    >
      <el-form-item label="查看方式"
        ><el-select v-model="filters.mode"
          ><el-option
            label="费用明细"
            value="events" /><el-option
            label="费用汇总"
            value="summary" /></el-select
      ></el-form-item>
      <el-form-item
        v-if="filters.mode === 'summary' && filters.scope === 'project'"
        label="汇总维度"
        ><el-select v-model="filters.groupBy"
          ><el-option
            v-for="(label, value) in {
              project: '项目',
              user: '发起人',
              department: '任务归属部门',
              model: '模型',
              day: '日期',
            }"
            :key="value"
            :label="label"
            :value="value" /></el-select
      ></el-form-item>
      <el-form-item v-if="filters.mode === 'summary' && filters.scope === 'cost_center'" label="汇总维度">
        <el-select v-model="filters.costCenterGroupBy"><el-option label="成本中心" value="cost_center" /><el-option label="日期" value="day" /></el-select>
      </el-form-item>
      <el-form-item label="费用归属">
        <el-select v-model="filters.scope"><el-option label="项目任务" value="project" /><el-option label="管理成本中心" value="cost_center" /></el-select>
      </el-form-item>
      <el-form-item v-if="filters.scope === 'cost_center'" label="成本中心ID" prop="costCenterId">
        <el-input v-model="filters.costCenterId" placeholder="留空查询全部成本中心" clearable />
      </el-form-item>
      <el-form-item label="计价口径"
        ><el-select v-model="filters.purpose"
          ><el-option
            label="平台费用"
            value="platform" /><el-option
            label="采购费用"
            value="procurement" /></el-select
      ></el-form-item>
      <el-form-item
        label="币种"
        prop="currency"
        ><el-input
          v-model="filters.currency"
          placeholder="例如 CNY"
          clearable
      /></el-form-item>
      <el-form-item
        v-if="filters.mode === 'events'"
        label="费用状态"
        ><el-select
          v-model="filters.state"
          clearable
          ><el-option
            v-for="(label, value) in states"
            :key="value"
            :label="label"
            :value="value" /></el-select
      ></el-form-item>
      <el-form-item
        label="项目ID"
        v-if="filters.scope === 'project'"
        prop="projectId"
        ><el-input
          v-model="filters.projectId"
          clearable
      /></el-form-item>
      <el-form-item
        label="任务ID"
        v-if="filters.mode === 'events' && filters.scope === 'project'"
        prop="jobId"
        ><el-input
          v-model="filters.jobId"
          clearable
      /></el-form-item>
      <el-form-item
        label="发起人ID"
        v-if="filters.scope === 'project'"
        prop="userId"
        ><el-input
          v-model="filters.userId"
          clearable
      /></el-form-item>
      <el-form-item
        label="费用创建时间（上海时间，结束时刻不包含）"
        prop="timeRange"
      >
        <el-date-picker
          v-model="filters.timeRange"
          type="datetimerange"
          value-format="YYYY-MM-DD HH:mm:ss"
          start-placeholder="开始时刻"
          end-placeholder="结束时刻"
        />
      </el-form-item>
      <el-form-item label="操作"
        ><el-button
          type="primary"
          :loading="loading"
          @click="search"
          >查询</el-button
        ></el-form-item
      >
    </el-form>
    <p class="hint">
      按当前管理权限读取费用；采购费用要求全部管理范围。原始金额保留首次计价结果，有效金额包含后续调整，各币种不混算。
    </p>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <BillingSummary
      v-if="filters.mode === 'summary'"
      v-loading="loading"
      :summary="summary"
    />
    <el-table
      v-else
      v-loading="loading"
      :data="rows"
      empty-text="当前范围没有费用记录"
    >
      <el-table-column
        prop="id"
        label="费用ID"
        min-width="100"
      />
      <el-table-column
        prop="jobId"
        label="任务ID"
        min-width="100"
      />
      <el-table-column
        prop="currency"
        label="币种"
        width="85"
      />
      <el-table-column prop="costCenterId" label="成本中心ID" min-width="150" />
      <el-table-column
        label="原始金额"
        min-width="160"
        ><template #default="{ row }">{{ amount(row.amount) }}</template></el-table-column
      >
      <el-table-column
        label="有效金额"
        min-width="160"
        ><template #default="{ row }">{{ amount(row.effectiveAmount) }}</template></el-table-column
      >
      <el-table-column
        label="状态"
        width="100"
        ><template #default="{ row }">{{ states[row.state] }}</template></el-table-column
      >
      <el-table-column
        prop="createTime"
        label="创建时间"
        min-width="210"
      />
      <el-table-column
        label="操作"
        width="90"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            @click="select(row)"
            >明细</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-pagination
      v-if="filters.mode === 'events' && total > 0"
      v-model:current-page="page"
      :page-size="20"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="load"
    />
    <el-dialog
      :model-value="detailOpen"
      title="费用明细"
      :show-close="!adjustmentPending"
      :close-on-click-modal="!adjustmentPending"
      :close-on-press-escape="!adjustmentPending"
      width="min(960px, 95vw)"
      @close="closeDetail"
    >
      <p
        v-if="detailLoading"
        role="status"
      >
        正在读取明细…
      </p>
      <el-alert
        v-if="detailError"
        :title="detailError"
        type="error"
        :closable="false"
      />
      <template v-if="detail">
        <p v-if="detail.costCenterId">管理成本中心：{{ detail.costCenterId }}。</p>
        <p>
          {{ detail.purpose === 'platform' ? '平台费用' : '采购费用' }} · {{ detail.currency }} ·
          {{ states[detail.state] }}
        </p>
        <p>原始金额 {{ amount(detail.amount) }} · 有效金额 {{ amount(detail.effectiveAmount) }}</p>
        <p class="hint">
          计费对象 {{ detail.subjectId }} · 固定价格版本 {{ detail.priceVersionId }}
        </p>
        <h3>采用用量</h3>
        <p
          v-if="!Object.keys(detail.usage).length"
          class="hint"
        >
          尚无采用用量。
        </p>
        <dl v-else>
          <div
            v-for="(label, key) in usageLabels"
            :key="key"
          >
            <dt>{{ label }}</dt>
            <dd>{{ amount(detail.usage[key]) }}</dd>
          </div>
        </dl>
        <h3>计价明细</h3>
        <el-table
          :data="detail.lines"
          empty-text="暂无计价明细"
          ><el-table-column
            prop="itemCode"
            label="计价项" /><el-table-column
            prop="quantity"
            label="用量" /><el-table-column
            prop="unitQuantity"
            label="单位数量" /><el-table-column
            prop="unitPrice"
            label="单价" /><el-table-column
            prop="amount"
            label="金额"
        /></el-table>
        <BillingAdjustment
          :key="`${detail.id}:${detail.revision}`"
          :event="detail"
          @saved="adjustmentSaved"
          @pending="adjustmentPending = $event"
        />
        <h3>调整历史</h3>
        <el-table
          :data="detail.adjustments"
          empty-text="暂无调整"
          ><el-table-column
            prop="deltaAmount"
            label="调整金额" /><el-table-column
            prop="reason"
            label="原因" /><el-table-column
            prop="reconciliationLineId"
            label="对账依据ID" /><el-table-column
            prop="createTime"
            label="调整时间"
        /></el-table>
      </template>
    </el-dialog>
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
.hint {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.el-pagination {
  margin-top: 16px;
}
dl > div {
  display: flex;
  gap: 16px;
  margin: 8px 0;
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
dt {
  color: var(--el-text-color-secondary);
}
</style>
