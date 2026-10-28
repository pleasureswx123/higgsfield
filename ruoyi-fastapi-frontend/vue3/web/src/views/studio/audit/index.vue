<script setup>
import { computed } from 'vue'
import { useAuditLogs } from '@/composables/studio/useAuditLogs'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const { allowed, filters, rows, page, total, loading, error, selected, load, search, inspect } = useAuditLogs()
const detailsOpen = computed({ get: () => !!selected.value, set: (value) => { if (!value) selected.value = undefined } })
</script>

<template>
  <div class="app-container audit-page">
    <header><h2>业务审计</h2><el-button text @click="settings.toggleTheme()">切换主题</el-button></header>
    <p>查看管理范围内的操作历史与变更证据。记录只读，历史事实不会随项目删除而清除。</p>
    <el-alert v-if="!allowed" title="没有业务审计查询权限" type="warning" :closable="false" />
    <el-form inline @submit.prevent>
      <el-form-item label="对象类型"><el-input v-model="filters.objectType" maxlength="100" clearable placeholder="精确匹配" /></el-form-item>
      <el-form-item label="对象标识"><el-input v-model="filters.objectId" maxlength="255" clearable placeholder="精确匹配" /></el-form-item>
      <el-form-item label="操作者ID"><el-input v-model="filters.actorId" maxlength="19" clearable /></el-form-item>
      <el-form-item label="开始时间（上海）"><el-date-picker v-model="filters.from" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="含开始时间" /></el-form-item>
      <el-form-item label="结束时间（上海）"><el-date-picker v-model="filters.to" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="不含结束时间" /></el-form-item>
      <el-form-item><el-button :disabled="!allowed" :loading="loading" @click="search">查询</el-button></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="rows" empty-text="暂无可查看的审计记录">
      <el-table-column prop="id" label="记录ID" min-width="120" />
      <el-table-column label="操作者" min-width="120"><template #default="{ row }">{{ row.actorKind === 'system' ? '系统' : row.actorId }}</template></el-table-column>
      <el-table-column prop="objectType" label="对象类型" min-width="150" />
      <el-table-column prop="objectId" label="对象标识" min-width="160" show-overflow-tooltip />
      <el-table-column prop="action" label="操作" min-width="120" />
      <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
      <el-table-column prop="createTime" label="记录时间（含时区）" min-width="240" />
      <el-table-column label="证据" width="100"><template #default="{ row }"><el-button text @click="inspect(row)">查看差异</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load" />
    <el-dialog v-model="detailsOpen" title="操作差异" width="min(900px, 92vw)" destroy-on-close>
      <template v-if="selected">
        <p>{{ selected.objectType }} · {{ selected.objectId }} · {{ selected.action }}</p>
        <p class="reason">{{ selected.reason || '未填写原因' }}</p>
        <pre>{{ JSON.stringify(selected.diff, null, 2) }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
header { display: flex; align-items: center; justify-content: space-between; }
p { color: var(--el-text-color-secondary); }
.el-pagination { margin-top: 20px; }
pre { padding: 16px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); border: 1px solid var(--el-border-color); border-radius: 6px; overflow: auto; max-height: 60vh; white-space: pre-wrap; overflow-wrap: anywhere; }
.reason { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
