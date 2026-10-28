<script setup>
import { ref } from 'vue'
import useSettingsStore from '@/store/modules/settings'
import { useReconciliations } from '@/composables/studio/useReconciliations'
import { useReconciliationAction } from '@/composables/studio/useReconciliationAction'
import ReconciliationActionDialog from './ReconciliationActionDialog.vue'
import ReconciliationCreateDialog from './ReconciliationCreateDialog.vue'
const createRef = ref()
const settings = useSettingsStore()
const { allowed, filters, formRef, rows, total, page, loading, error, search, load, select,
  detailOpen, detail, detailLoading, detailError, lines, lineTotal, linePage, lineStatus,
  loadDetail, filterLines, closeDetail, downloading, downloadError, download } = useReconciliations()
const { allowed: actionAllowed, target: actionTarget, pending: actionPending, error: actionError,
  form: actionForm, formRef: actionFormRef, canStart, start: startAction, close: closeAction,
  submit: submitAction } = useReconciliationAction(async () => { await Promise.all([load(), loadDetail()]) })
const batchStates = { imported: '已受理', matching: '匹配中', confirmed: '已确认', disputed: '有差异' }
const importStates = { pending: '待处理', processed: '已解析', failed: '解析失败' }
const lineStates = { unmatched: '未匹配', matched: '已匹配', confirmed: '已确认', disputed: '有差异' }
const outcomes = { original: '首次记录', duplicate: '重复证据', conflict: '冲突证据' }
const rules = { accountId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效供应商账号ID', trigger: 'blur' }] }
</script>

<template>
  <div class="app-container reconciliation-console">
    <header><h2>供应商账单对账</h2><div>
      <el-button type="primary" :disabled="!actionAllowed" @click="createRef?.start()">导入账单</el-button>
      <el-button @click="settings.toggleTheme()">{{ settings.isDark ? '切换亮色' : '切换暗色' }}</el-button>
    </div></header>
    <p>对账按原币种保留真实账单；匹配与确认不会自动调整平台估值。</p>
    <el-alert v-if="!allowed" title="需要费用读取权限及全部管理范围" type="warning" :closable="false" />
    <el-form ref="formRef" :model="filters" :rules="rules" inline label-position="top">
      <el-form-item label="供应商账号ID" prop="accountId"><el-input v-model="filters.accountId" clearable /></el-form-item>
      <el-form-item label="批次状态"><el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 180px">
        <el-option v-for="(label, value) in batchStates" :key="value" :label="label" :value="value" />
      </el-select></el-form-item>
      <el-form-item><el-button type="primary" :disabled="!allowed" :loading="loading" @click="search">查询</el-button></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="rows" row-key="id" empty-text="暂无对账批次">
      <el-table-column prop="id" label="批次ID" min-width="100" />
      <el-table-column prop="accountId" label="账号ID" min-width="100" />
      <el-table-column label="账期" min-width="280"><template #default="{ row }">{{ row.periodStart }} 至 {{ row.periodEnd }}</template></el-table-column>
      <el-table-column label="导入" width="100"><template #default="{ row }">{{ importStates[row.importState] }}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }">{{ batchStates[row.status] }}</template></el-table-column>
      <el-table-column label="文件行 / 已匹配 / 差异" min-width="180"><template #default="{ row }">{{ row.counts.total }} / {{ row.counts.matched }} / {{ row.counts.disputed }}</template></el-table-column>
      <el-table-column label="操作" width="100"><template #default="{ row }"><el-button text type="primary" :disabled="!allowed" @click="select(row)">查看明细</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="load" />
    <el-dialog :model-value="detailOpen" title="账单文件明细" width="min(1200px, 96vw)"
      :show-close="!actionTarget" :close-on-click-modal="!actionTarget" :close-on-press-escape="!actionTarget" @close="closeDetail">
      <div v-loading="detailLoading">
        <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
        <template v-if="detail">
          <p>批次 {{ detail.id }} · {{ importStates[detail.importState] }} · {{ batchStates[detail.status] }}</p>
          <p v-if="detail.attachment">原始文件：{{ detail.attachment.fileName }}
            <el-button text type="primary" :loading="downloading" :disabled="!allowed || detailLoading" @click="download">下载账单</el-button>
          </p>
          <el-alert v-if="downloadError" :title="downloadError" type="error" :closable="false" />
          <el-alert v-if="detail.importError" :title="`${detail.importError.message}（行号 ${detail.importError.lineNo}）`" type="error" :closable="false" />
          <el-alert v-else-if="detail.importState === 'pending'" title="文件已受理，等待对账处理器解析。可稍后刷新查看。" type="info" :closable="false" />
        </template>
        <div class="line-controls"><el-select v-model="lineStatus" :disabled="!!actionTarget" clearable placeholder="全部账单项状态" @change="filterLines" style="width: 220px">
          <el-option v-for="(label, value) in lineStates" :key="value" :label="label" :value="value" />
        </el-select><el-button text type="primary" :disabled="!allowed || !!actionTarget" @click="loadDetail">刷新明细</el-button></div>
        <p>首次金额与各次文件证据均保留。最近采用金额记录人工选择；出现新差异时需重新处理和确认。重复行不代表重复费用。</p>
        <el-table :data="lines" row-key="observationId" empty-text="暂无符合条件的文件行">
          <el-table-column prop="lineNo" label="文件行" width="80" />
          <el-table-column prop="externalLineKey" label="供应商账单项" min-width="150" />
          <el-table-column label="首次金额" min-width="185"><template #default="{ row }">{{ row.amount }} {{ row.currency }}</template></el-table-column>
          <el-table-column label="本次文件金额" min-width="185"><template #default="{ row }">{{ row.sourceEvidence.amount }} {{ row.sourceEvidence.currency }}</template></el-table-column>
          <el-table-column label="证据" width="100"><template #default="{ row }">{{ outcomes[row.outcome] }}</template></el-table-column>
          <el-table-column label="状态" width="100"><template #default="{ row }">{{ lineStates[row.status] }}</template></el-table-column>
          <el-table-column label="计费对象ID" min-width="110"><template #default="{ row }">{{ row.subjectId || '未匹配' }}</template></el-table-column>
          <el-table-column label="最近采用金额" min-width="185"><template #default="{ row }">{{ row.acceptedAmount == null ? '尚未另选证据' : `${row.acceptedAmount} ${row.acceptedCurrency}` }}</template></el-table-column>
          <el-table-column label="操作" width="270" fixed="right"><template #default="{ row }">
            <el-button text type="primary" :disabled="detailLoading || !!actionTarget || !canStart(row, 'match')" @click="startAction(row, 'match')">匹配</el-button>
            <el-button text type="primary" :disabled="detailLoading || !!actionTarget || !canStart(row, 'confirm')" @click="startAction(row, 'confirm')">确认</el-button>
            <el-button v-if="row.status === 'disputed'" text type="primary" :disabled="detailLoading || !!actionTarget || !canStart(row, 'resolve')" @click="startAction(row, 'resolve')">采用此行证据</el-button>
          </template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="linePage" :disabled="!!actionTarget" :page-size="20" :total="lineTotal" layout="total, prev, pager, next" @current-change="loadDetail" />
      </div>
    </el-dialog>
    <ReconciliationActionDialog ref="actionFormRef" :target="actionTarget" :pending="actionPending"
      :error="actionError" :allowed="actionAllowed" :model="actionForm"
      @update:subject-id="actionForm.subjectId = $event" @update:reason="actionForm.reason = $event"
      @close="closeAction" @submit="submitAction" />
    <ReconciliationCreateDialog ref="createRef" @saved="load" />
  </div>
</template>

<style scoped>
header, .line-controls { display: flex; gap: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.line-controls { justify-content: flex-start; margin: 16px 0; }
.el-pagination { margin-top: 20px; }
p { color: var(--el-text-color-regular); overflow-wrap: anywhere; }
</style>
