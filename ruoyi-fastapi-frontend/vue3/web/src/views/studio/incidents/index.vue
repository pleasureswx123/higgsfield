<script setup>
import { computed } from 'vue'
import { useIncidents } from '@/composables/studio/useIncidents'
import { useIncidentRecovery } from '@/composables/studio/useIncidentRecovery'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const { allowed, filters, rows, page, total, loading, error, selectedId, detail, detailLoading, detailError, load, search, inspect, close } = useIncidents()
const { allowed: canRecover, target, pending, uncertain, error: actionError, form, formRef, start, close: closeRecovery, submit } = useIncidentRecovery(load)
const open = computed({ get: () => !!selectedId.value, set: value => { if (!value) close() } })
const actionOpen = computed({ get: () => !!target.value, set: value => { if (!value) closeRecovery() } })
const states = { submission_unknown:'提交未知', blocked:'编排阻塞', upstream_unknown:'上游未知', upstream_failed:'上游失败', archive_failed:'归档失败', source_expired:'归档源过期', billing_disputed:'费用争议' }
const actionLabels = { retry_archive: '重试归档', requery: '重新查询', close_tracking: '关闭本地追踪', confirm_not_accepted: '确认未受理' }
</script>
<template>
  <div class="app-container">
    <header><h2>异常任务</h2><el-button text @click="settings.toggleTheme()">切换主题</el-button></header>
    <p>依据已记录的任务、上游、归档与费用状态定位异常。未知受理不能直接视为失败或免费。</p>
    <el-form inline @submit.prevent>
      <el-form-item label="项目ID"><el-input v-model="filters.projectId" clearable maxlength="19" /></el-form-item>
      <el-form-item label="异常类型"><el-select v-model="filters.state" clearable style="width:180px"><el-option v-for="(label,value) in states" :key="value" :label="label" :value="value" /></el-select></el-form-item>
      <el-form-item><el-button :disabled="!allowed" :loading="loading" @click="search">查询</el-button></el-form-item>
    </el-form>
    <el-alert v-if="!allowed" title="没有运行治理读取权限" type="warning" :closable="false" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="rows" empty-text="暂无符合条件的可见异常任务">
      <el-table-column prop="jobId" label="任务ID" min-width="120" /><el-table-column prop="projectId" label="项目ID" min-width="120" />
      <el-table-column prop="actorId" label="发起者ID" min-width="120" /><el-table-column prop="orchestrationState" label="编排阶段" min-width="150" />
      <el-table-column prop="upstreamState" label="上游状态" min-width="120" /><el-table-column prop="billingState" label="费用状态" min-width="120" />
      <el-table-column prop="lastKnownFact" label="最后已知事实" min-width="300" show-overflow-tooltip />
      <el-table-column prop="nextActionAt" label="下次调度（含时区）" min-width="230" />
      <el-table-column label="操作" width="100"><template #default="{row}"><el-button text @click="inspect(row.jobId)">查看详情</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="load" />
    <el-dialog v-model="open" title="异常任务状态" width="min(900px, 92vw)" destroy-on-close>
      <div v-loading="detailLoading" class="details">
        <p>任务ID：{{ selectedId }}</p>
        <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
        <el-button v-if="detailError" text @click="inspect(selectedId)">重新读取</el-button>
        <template v-if="detail">
          <p>{{ detail.lastKnownFact }}</p><p>修订号：{{ detail.revision }} · 最近更新时间：{{ detail.updateTime }}</p>
          <p>归档：共 {{ detail.archiveSummary.total }} 项，已就绪 {{ detail.archiveSummary.ready }} 项，失败或过期 {{ detail.archiveSummary.failed }} 项，待处理 {{ detail.archiveSummary.pending }} 项。</p>
          <p>证据定位：{{ detail.evidenceRefs.join('、') || '暂无调用证据' }}</p>
          <el-button v-if="canRecover && detail.allowedActions.includes('retry_archive')" :disabled="pending || uncertain" @click="start(detail)">重试归档</el-button>
          <el-button v-if="canRecover && detail.allowedActions.includes('requery')" :disabled="pending || uncertain" @click="start(detail, 'requery')">重新查询</el-button>
          <el-button v-if="canRecover && detail.allowedActions.includes('close_tracking')" :disabled="pending || uncertain" @click="start(detail, 'close_tracking')">关闭本地追踪</el-button>
          <el-button v-if="canRecover && detail.allowedActions.includes('confirm_not_accepted')" :disabled="pending || uncertain" @click="start(detail, 'confirm_not_accepted')">确认未受理</el-button>
        </template>
      </div>
    </el-dialog>
    <el-dialog v-model="actionOpen" :title="actionLabels[target?.action] || '异常处理'" width="min(620px, 92vw)" :close-on-click-modal="!pending && !uncertain" :close-on-press-escape="!pending && !uncertain" :show-close="!pending && !uncertain">
      <p v-if="target?.action === 'confirm_not_accepted'">必须引用同一提交的明确拒绝调用证据（provider-call:编号）。确认后结束本地任务，不覆盖原未知调用、不重新生成、不宣称免费或释放费用预占。</p>
      <p v-else-if="target?.action === 'close_tracking'">停止此任务的本地自动状态核查，保留为阻塞状态。不取消供应商任务、不代表免费或释放费用预占；独立归档和费用处理仍继续。必须填写关闭依据。</p>
      <p v-else-if="target?.action === 'requery'">提前调度已有任务核查：提交未知的图片和视频核查本地已保存响应，已有供应商任务编号的视频请求查询接口。不重新提交生成，也不宣称供应商查询免费。</p>
      <p v-else>仅重新调度此任务已有的失败媒体归档，不创建新模型任务。所有失败输出的来源必须仍然有效。</p>
      <p>任务 {{ target?.jobId }} · 修订 {{ target?.revision }}</p>
      <el-form ref="formRef" :model="form" label-position="top" @submit.prevent>
        <el-form-item label="处理原因" prop="reason" :rules="[{required:true, whitespace:true, message:'请填写处理原因', trigger:'blur'}]"><el-input v-model="form.reason" type="textarea" maxlength="4000" :disabled="pending || uncertain" /></el-form-item>
        <el-form-item :label="['close_tracking', 'confirm_not_accepted'].includes(target?.action) ? '证据引用（必填）' : '证据引用（可选，如 ticket:123）'" prop="evidenceRef" :rules="['close_tracking', 'confirm_not_accepted'].includes(target?.action) ? [{required:true, whitespace:true, message:'请填写证据引用', trigger:'blur'}] : []"><el-input v-model="form.evidenceRef" maxlength="255" :disabled="pending || uncertain" /></el-form-item>
      </el-form>
      <el-alert v-if="uncertain" title="原处理请求结果尚未确认，请使用原请求重试确认；暂不能修改内容或离开。" type="warning" :closable="false" />
      <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" />
      <template #footer><el-button :disabled="pending || uncertain" @click="closeRecovery">取消</el-button><el-button :loading="pending" :disabled="!canRecover" @click="submit">{{ uncertain ? '重试确认原请求' : '提交处理' }}</el-button></template>
    </el-dialog>
  </div>
</template>
<style scoped>
header { display:flex; align-items:center; justify-content:space-between; }
p { color:var(--el-text-color-secondary); overflow-wrap:anywhere; }
.el-pagination { margin-top:20px; }
.details { min-height:100px; }
</style>
