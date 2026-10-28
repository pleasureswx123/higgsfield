<script setup>
import { computed } from 'vue'
import { useProviderCalls } from '@/composables/studio/useProviderCalls'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const { allowed, filters, rows, page, total, loading, error, selectedId, detail, detailLoading, detailError, load, search, inspect, close } = useProviderCalls()
const open = computed({ get: () => !!selectedId.value, set: value => { if (!value) close() } })
const states = { planned: '计划中', sending: '发送中', completed: '调用完成', unknown: '结果未知' }
const acceptance = { accepted: '已受理', rejected: '未受理', unknown: '受理未知', not_applicable: '不适用' }
</script>
<template>
  <div class="app-container">
    <header><h2>供应商调用记录</h2><el-button text @click="settings.toggleTheme()">切换主题</el-button></header>
    <p>调用完成不代表生成成功或费用为零。时间筛选按调用记录创建时间，开始时间包含、结束时间不包含。</p>
    <el-alert v-if="!allowed" title="没有运行治理查询权限" type="warning" :closable="false" />
    <el-form inline @submit.prevent>
      <el-form-item label="任务ID"><el-input v-model="filters.jobId" maxlength="19" clearable /></el-form-item>
      <el-form-item label="供应商账号ID"><el-input v-model="filters.accountId" maxlength="19" clearable /></el-form-item>
      <el-form-item label="状态"><el-select v-model="filters.state" clearable style="width:160px"><el-option v-for="(label,value) in states" :key="value" :label="label" :value="value" /></el-select></el-form-item>
      <el-form-item label="开始时间（上海）"><el-date-picker v-model="filters.from" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" /></el-form-item>
      <el-form-item label="结束时间（上海）"><el-date-picker v-model="filters.to" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" /></el-form-item>
      <el-form-item><el-button :disabled="!allowed" :loading="loading" @click="search">查询</el-button></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="rows" empty-text="暂无可查看的调用记录">
      <el-table-column prop="id" label="调用ID" min-width="120" />
      <el-table-column prop="jobId" label="任务ID" min-width="120" />
      <el-table-column prop="costCenterId" label="成本中心ID" min-width="120" />
      <el-table-column prop="operation" label="操作" min-width="120" />
      <el-table-column label="调用状态" min-width="120"><template #default="{row}">{{ states[row.state] }}</template></el-table-column>
      <el-table-column label="受理事实" min-width="120"><template #default="{row}">{{ acceptance[row.acceptance] }}</template></el-table-column>
      <el-table-column prop="httpStatus" label="HTTP状态" width="110" />
      <el-table-column prop="businessCode" label="业务码" min-width="120" />
      <el-table-column prop="startedAt" label="开始发送（含时区）" min-width="240" />
      <el-table-column prop="finishedAt" label="记录结束（含时区）" min-width="240" />
      <el-table-column label="证据" width="100"><template #default="{row}"><el-button text @click="inspect(row.id)">查看详情</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load" />
    <el-dialog v-model="open" title="脱敏调用证据" width="min(900px, 92vw)" destroy-on-close>
      <div v-loading="detailLoading" class="evidence">
        <p>调用ID：{{ selectedId }}</p>
        <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
        <el-button v-if="detailError" text @click="inspect(selectedId)">重新读取</el-button>
        <template v-if="detail"><h3>请求元数据</h3><pre>{{ JSON.stringify(detail.requestMetadata, null, 2) }}</pre><h3>响应元数据</h3><pre>{{ JSON.stringify(detail.responseMetadata, null, 2) }}</pre></template>
      </div>
    </el-dialog>
  </div>
</template>
<style scoped>
header { display:flex; align-items:center; justify-content:space-between; }
p { color:var(--el-text-color-secondary); }
.el-pagination { margin-top:20px; }
.evidence { min-height:100px; }
pre { padding:16px; background:var(--el-fill-color-light); color:var(--el-text-color-primary); border:1px solid var(--el-border-color); border-radius:6px; white-space:pre-wrap; overflow-wrap:anywhere; max-height:45vh; overflow:auto; }
</style>
