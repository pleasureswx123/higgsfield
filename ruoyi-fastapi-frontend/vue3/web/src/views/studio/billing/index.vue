<script setup>
import { computed, ref } from 'vue'
import { useBillingEvents } from '@/composables/studio/useBillingEvents'
import BillingAdjustment from './BillingAdjustment.vue'
import BillingSummary from './BillingSummary.vue'
import { billingTimeWindow } from '@/utils/billingQuery'
const adjustmentPending = ref(false)
function adjustmentSaved() {
  adjustmentPending.value = false
  void load()
}
const {
  consumers, consumersLoading, consumersError, searchConsumers,
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
  reset,
  load,
  select,
  closeDetail,
} = useBillingEvents()
const states = { pending: '待确认', calculated: '已计算', confirmed: '已确认', disputed: '有争议', unpriced: '未计价' }
const usageLabels = {
  inputTokens: '输入 Token',
  outputTokens: '输出 Token',
  videoTokens: '视频 Token',
  imageCount: '图片数量',
  outputSeconds: '输出秒数',
  referenceSeconds: '参考秒数',
}
// 空值不代表零；图片、视频及非项目费用共用实际已记录的用量展示。
const recordedUsage = computed(() => Object.entries(usageLabels)
  .filter(([key]) => detail.value?.usage?.[key] != null && detail.value.usage[key] !== '')
  .map(([key, label]) => ({ key, label, value: detail.value.usage[key] })))
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
  projectId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效的项目编号', trigger: 'blur' }],
  jobId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效的任务编号', trigger: 'blur' }],
  costCenterId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效的成本中心ID', trigger: 'blur' }],
}
// 保留十进制字符串，不经浮点数转换；未知金额不能显示为零。
const amount = (value) => (value == null ? '待核算' : String(value))
</script>

<template>
  <div class="app-container billing-console">
    <el-alert v-if="!allowed" title="没有费用读取权限或会话已失效" type="warning" :closable="false" />
    <div class="heading">
      <h2>用量与费用</h2>

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
        <el-select v-model="filters.scope"><el-option label="项目创作" value="project" /><el-option label="管理员测试等非项目消耗" value="cost_center" /></el-select>
      </el-form-item>
      <el-form-item v-if="filters.scope === 'cost_center'" label="成本中心ID" prop="costCenterId">
        <el-input v-model="filters.costCenterId" placeholder="留空查询全部成本中心" clearable />
      </el-form-item>
      <el-form-item label="计价口径"
        ><el-select v-model="filters.purpose"
          ><el-option
            label="项目记账金额"
            value="platform" /><el-option
            label="供应商成本"
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
        label="项目编号"
        v-if="filters.scope === 'project'"
        prop="projectId"
        ><el-input
          v-model="filters.projectId"
          clearable
      /></el-form-item>
      <el-form-item
        label="任务编号"
        v-if="filters.mode === 'events' && filters.scope === 'project'"
        prop="jobId"
        ><el-input
          v-model="filters.jobId"
          clearable
      /></el-form-item>
      <el-form-item
        label="发起人"
        v-if="filters.scope === 'project'"
        prop="userId"
        ><el-select
          v-model="filters.userId"
          filterable
          remote
          :remote-method="searchConsumers"
          :loading="consumersLoading"
          :no-data-text="consumersError || '没有匹配的发起人'"
          placeholder="全部发起人"
          @visible-change="(visible) => visible && searchConsumers()"
          clearable
        >
          <el-option v-for="person in consumers" :key="person.id" :value="person.id"
            :label="person.username ? `${person.name || person.username}（${person.username}）` : (person.name || `用户 ${person.id}`)" />
        </el-select></el-form-item>
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
          >查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item
      >
    </el-form>
    <p class="hint">
      {{ filters.scope === 'cost_center' ? '这里查看管理员测试等不属于制作项目的消耗。' : '这里查看成员在制作项目中生成图片、视频的消耗。' }}
      {{ filters.purpose === 'procurement' ? '供应商成本用于核对供应商账单。' : '项目记账金额用于统计项目内部使用费用。' }}
      同一次生成的两种金额不能相加，避免重复统计。未计价记录的金额待核算，不计入费用汇总。
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
      row-key="rowKey"
      empty-text="当前范围没有费用记录"
    >
      <el-table-column
        prop="id"
        label="费用ID"
        min-width="100"
      ><template #default="{ row }">{{ row.id ?? '尚未计价' }}</template></el-table-column>
      <el-table-column
        prop="jobId"
        label="任务编号"
        min-width="100"
      />
      <el-table-column
        prop="currency"
        label="币种"
        width="85"
      />
      <el-table-column label="消耗人" min-width="190" show-overflow-tooltip>
        <template #default="{ row }">
          <div>{{ row.consumerName || row.consumerUsername || (row.consumerId ? `用户 ${row.consumerId}` : '未记录') }}</div>
          <small v-if="row.consumerUsername" class="hint">{{ row.consumerUsername }}</small>
        </template>
      </el-table-column>
      <el-table-column v-if="filters.scope === 'cost_center'" prop="costCenterId" label="成本中心ID" min-width="150" />
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
    <el-drawer
      :model-value="detailOpen"
      title="费用明细"
      :show-close="!adjustmentPending"
      :close-on-click-modal="!adjustmentPending"
      :close-on-press-escape="!adjustmentPending"
      size="min(960px, 95vw)"
      append-to-body
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
        <el-alert v-if="detail.reason" :title="detail.reason" type="warning" :closable="false" show-icon />
        <p v-if="detail.costCenterId">管理成本中心：{{ detail.costCenterId }}。</p>
        <p>
          {{ detail.purpose === 'platform' ? '项目记账金额' : '供应商成本' }} · {{ detail.currency }} ·
          {{ states[detail.state] }}
        </p>
        <p>原始金额 {{ amount(detail.amount) }} · 有效金额 {{ amount(detail.effectiveAmount) }}</p>
        <p class="hint">
          计费对象 {{ detail.subjectId }} <span v-if="detail.priceVersionId">· 固定价格版本 {{ detail.priceVersionId }}</span>
        </p>
        <h3>{{ detail.id ? '采用用量' : '实际记录用量' }}</h3>
        <p
          v-if="!recordedUsage.length"
          class="hint"
        >
          暂无已记录的用量数据，费用是否已核算请查看上方费用状态。
        </p>
        <dl v-else>
          <div
            v-for="{ key, label, value } in recordedUsage"
            :key="key"
          >
            <dt>{{ label }}</dt>
            <dd>{{ value }}</dd>
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
          v-if="detail.id"
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
      <template #footer><el-button :disabled="adjustmentPending" @click="closeDetail">关闭明细</el-button></template>
    </el-drawer>
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
