<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { IconStack2, IconSearch, IconArrowUpRight, IconPhoto, IconVideo, IconX } from '@tabler/icons-vue'
import { ElDrawer } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import type { GenerationSummary } from '@/api/generations'
const props = defineProps<{
  acceptedId?: string; submitting?: boolean; awaiting?: boolean
  rows: GenerationSummary[]; error: string; loading: boolean; autoUpdating: boolean; lastChecked?: number
  label: (row: GenerationSummary) => string
}>()
const emit = defineEmits<{ refresh: []; detail: [id: string] }>()
const route = useRoute(), router = useRouter()
const opened = ref(false)
const notice = ref<GenerationSummary>()
const running = (row: GenerationSummary) => !['finished', 'blocked', 'submission_unknown'].includes(row.orchestrationState) && !['failed', 'cancelled'].includes(row.upstreamState)
const queued = (row: GenerationSummary) => ['accepted', 'preparing'].includes(row.orchestrationState)
const active = computed(() => props.rows.filter(running))
const queueCount = computed(() => active.value.filter(queued).length)
const workingCount = computed(() => active.value.length - queueCount.value)
type Filter = 'all' | 'active' | 'attention' | 'done'
const filter = ref<Filter>('all')
const search = ref('')
const category = (row: GenerationSummary): Filter => running(row) || row.archiveSummary.pending > 0 ? 'active'
  : row.orchestrationState === 'submission_unknown' || row.orchestrationState === 'blocked' || row.upstreamState === 'failed' || row.archiveSummary.failed > 0 ? 'attention' : 'done'
const filters: { id: Filter; label: string }[] = [{ id: 'all', label: '全部' }, { id: 'active', label: '进行中' }, { id: 'attention', label: '需处理' }, { id: 'done', label: '已结束' }]
const count = (id: Filter) => id === 'all' ? props.rows.length : props.rows.filter(row => category(row) === id).length
const visibleRows = computed(() => props.rows.filter(row => (filter.value === 'all' || category(row) === filter.value)
  && `${row.promptExcerpt || ''} ${row.id}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const date = (value: string) => new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
const known = new Map<string, string>()
let initialized = false
const status = (row: GenerationSummary) => `${row.orchestrationState}:${row.upstreamState}:${row.archiveSummary.ready}:${row.archiveSummary.failed}:${row.archiveSummary.pending}`
watch(() => props.rows, rows => {
  if (!rows.length) { known.clear(); initialized = false; notice.value = undefined; return }
  for (const row of rows) {
    const previous = known.get(row.id)
    if ((initialized && previous && previous !== status(row) && !running(row)) || (row.id === props.acceptedId && !previous)) notice.value = row
    if (notice.value?.id === row.id) notice.value = row
    known.set(row.id, status(row))
  }
  if (rows.length) initialized = true
}, { immediate: true })
watch(() => props.acceptedId, () => { notice.value = undefined })
watch(() => route.params.id, () => { known.clear(); initialized = false; notice.value = undefined; opened.value = false })
const title = (row: GenerationSummary) => row.promptExcerpt || `${row.kind === 'video' ? '视频' : '图片'}创作`
const action = (row: GenerationSummary) => row.archiveSummary.ready ? '查看结果' : row.orchestrationState === 'submission_unknown' ? '核查详情' : ['failed', 'cancelled'].includes(row.upstreamState) || row.orchestrationState === 'blocked' ? '查看原因' : '查看任务'
function view(row: GenerationSummary) { emit('detail', row.id) }
function history() { opened.value = false; void router.push({ path: route.path, query: { ...route.query, tab: 'generations' } }) }
</script>

<template>
  <section class="creation-activity" aria-label="项目生成任务">
    <button class="task-entry" type="button" :aria-expanded="opened" @click="opened = true">
      <span v-if="submitting || workingCount" class="activity-spinner" aria-hidden="true"></span>
      <IconStack2 :size="18" aria-hidden="true" /><strong>任务中心</strong>
      <span>{{ submitting ? '提交中…' : active.length ? `处理中 ${workingCount} · 排队 ${queueCount}` : count('attention') ? `${count('attention')} 项需处理` : '' }}</span>
      <span v-if="error" class="error-dot">更新中断</span>
    </button>
    <div v-if="notice && !opened" class="task-notice">
      <button class="notice-close" type="button" aria-label="关闭任务通知" @click="notice = undefined">×</button>
      <p class="notice-title" :title="title(notice)">{{ title(notice) }}</p>
      <p role="status">{{ label(notice) }}</p>
      <button type="button" class="task-link" @click="view(notice)">{{ action(notice) }}</button>
    </div>
    <p v-if="error && !opened" class="connection-error" role="status">暂时无法更新任务状态。<button class="task-link" :disabled="loading" @click="emit('refresh')">重新连接</button></p>
    <span class="sr-only" role="status">{{ submitting ? '正在提交创作' : awaiting ? '任务已受理，可继续创作' : '' }}</span>
  </section>
  <ElDrawer v-model="opened" title="任务中心" class="generation-task-drawer" size="min(480px, 100vw)" :show-close="false" direction="rtl" append-to-body destroy-on-close>
    <template #header="{ titleId, titleClass, close }">
      <div class="drawer-heading"><span class="drawer-symbol"><IconStack2 :size="24" /></span><div><h2 :id="titleId" :class="titleClass">任务中心</h2><p>跟踪本项目的创作进度与结果</p></div><button class="drawer-close" type="button" aria-label="关闭任务中心" @click="close"><IconX :size="20" /></button></div>
    </template>
    <div class="task-panel">
      <div class="panel-controls">
        <div class="panel-heading"><span>我的生成任务</span><button type="button" class="history-link" @click="history">完整记录 <IconArrowUpRight :size="14" /></button></div>
        <label class="task-search"><IconSearch :size="17" aria-hidden="true" /><input v-model="search" type="search" placeholder="搜索提示词或任务编号" aria-label="搜索任务" /></label>
        <div class="task-filters" aria-label="任务状态筛选"><button v-for="item in filters" :key="item.id" type="button" :aria-pressed="filter === item.id" @click="filter = item.id">{{ item.label }} <span>{{ count(item.id) }}</span></button></div>
      </div>
      <p v-if="error" class="panel-error" role="alert">状态暂未更新，以下是上次结果。<button class="task-link" :disabled="loading" @click="emit('refresh')">重新连接</button></p>
      <div v-if="!visibleRows.length" class="task-empty"><IconStack2 :size="32" /><strong>{{ loading && !rows.length ? '正在读取任务' : search ? '没有匹配的任务' : '这里暂时没有任务' }}</strong><p>{{ search ? '换个关键词，或清除搜索后查看。' : '提交创作后，可在这里查看进度与结果。' }}</p><button v-if="search" class="task-link" @click="search = ''">清除搜索</button></div>
      <div class="task-list">
        <article v-for="row in visibleRows" :key="row.id" class="task-card" :data-state="category(row)">
          <div class="task-card-top"><span class="task-kind"><IconVideo v-if="row.kind === 'video'" :size="16" /><IconPhoto v-else :size="16" />{{ row.kind === 'video' ? '视频' : '图片' }}</span><span class="status-badge">{{ category(row) === 'active' ? queued(row) ? '排队中' : row.archiveSummary.pending ? '保存中' : '生成中' : category(row) === 'attention' ? '需处理' : row.archiveSummary.ready ? '已完成' : '已结束' }}</span></div>
          <h3 :title="title(row)">{{ title(row) }}</h3>
          <p class="task-meta">{{ date(row.createTime) }} · #{{ row.id }}</p>
          <p class="task-result">{{ label(row) }}</p>
          <p v-if="category(row) === 'active'" class="task-meta">{{ queued(row) ? '等待可用名额，可以继续创作。' : '后台处理中，离开页面不会取消任务。' }}</p>
          <p v-else-if="row.orchestrationState === 'submission_unknown'" class="task-meta">未取得完整结果，请管理员核查。不会自动重新生成。</p>
          <div class="task-card-bottom"><button type="button" class="task-action" @click="view(row)">{{ action(row) }} <IconArrowUpRight :size="14" /></button></div>
        </article>
      </div>
    </div>
    <template #footer><p class="panel-footer">关闭面板不会取消任务，也不会重新提交生成。</p></template>
  </ElDrawer>
</template>

<style scoped>
.creation-activity { width:100%; margin:8px 0; color:var(--foreground); min-width:0; }
.task-entry,.task-notice,.connection-error { border:1px solid var(--border); border-radius:12px; background:var(--surface); box-shadow:none; }
button { font:inherit; cursor:pointer; color:inherit; }
.task-entry { display:flex; align-items:center; gap:8px; width:100%; padding:12px 10px; flex-wrap:wrap; font-size:12px; text-align:left; }
.task-entry > strong { flex:1; }
.task-entry > span:not(.activity-spinner) { flex-basis:100%; margin-left:26px; color:var(--muted-foreground); font-size:11px; }
.task-entry > span:empty { display:none; }
.task-entry .activity-spinner { display:none; }
.task-notice { position:relative; margin-top:8px; padding:14px 32px 14px 14px; font-size:13px; }
.task-notice p { margin:0 0 8px; }
.notice-title { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:600; }
.notice-close { position:absolute; right:8px; top:8px; border:0; background:transparent; font-size:20px; }
.task-link { border:0; background:transparent; padding:2px 0; color:var(--foreground); text-decoration:underline; text-underline-offset:3px; font-size:12px; }
.connection-error { padding:12px; font-size:12px; }
.error-dot { color:var(--el-color-danger); }
button:focus-visible { outline:2px solid var(--focus); outline-offset:3px; }
button:disabled { opacity:.5; cursor:wait; }
.panel-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.task-panel { color:var(--foreground); }
.task-card { padding:18px; margin-bottom:12px; border:1px solid var(--border); border-radius:12px; background:var(--surface-raised); }
.task-card h3 { margin:0; font-size:14px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.task-card p { font-size:13px; margin:8px 0; }
.task-meta { color:var(--muted-foreground); font-size:12px; }
.activity-spinner { width:12px; height:12px; border:2px solid var(--muted-foreground); border-right-color:transparent; border-radius:50%; animation:activity-spin 1s linear infinite; flex-shrink:0; }
.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
@keyframes activity-spin { to { transform:rotate(360deg); } }
@media(prefers-reduced-motion:reduce) { .activity-spinner { animation:none; } }

.drawer-close { margin-left:auto; display:grid; place-items:center; width:32px; height:32px; border:0; border-radius:8px; background:var(--surface-hover); }
.drawer-heading { width:100%; display:flex; gap:12px; align-items:center; }
.drawer-heading h2 { margin:0; font-size:20px; font-weight:650; color:var(--foreground); }
.drawer-heading p { margin:5px 0 0; font-size:12px; color:var(--muted-foreground); }
.drawer-symbol { display:grid; place-items:center; width:44px; height:44px; border-radius:14px; background:var(--surface-hover); color:var(--foreground); }
.panel-controls { position:sticky; top:-20px; z-index:1; background:var(--surface); padding:0 0 16px; }
.panel-heading { font-size:12px; color:var(--muted-foreground); }
.history-link,.task-action { display:inline-flex; align-items:center; justify-content:center; gap:6px; border:1px solid var(--border); border-radius:8px; padding:8px 12px; background:var(--surface); font-size:12px; color:var(--foreground); }
.history-link { border:0; padding:4px 0; }
.task-search { display:flex; align-items:center; gap:8px; padding:10px 12px; border:1px solid var(--border); border-radius:10px; background:var(--surface-raised); color:var(--muted-foreground); }
.task-search:focus-within { outline:2px solid var(--focus); }
.task-search input { width:100%; min-width:0; font:inherit; font-size:13px; background:transparent; color:var(--foreground); outline:none; border:0; }
.task-filters { display:flex; gap:4px; margin-top:14px; padding:4px; background:var(--surface-hover); border-radius:10px; }
.task-filters button { flex:1; white-space:nowrap; border:0; background:transparent; border-radius:7px; padding:9px 4px; font-size:12px; }
.task-filters button[aria-pressed="true"] { background:var(--surface); box-shadow:0 1px 4px #0001; font-weight:650; }
.task-filters span { font-size:11px; color:var(--muted-foreground); }
.task-card-top,.task-card-bottom { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.task-card-bottom { justify-content:flex-end; margin:14px 0 0; }
.task-kind { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted-foreground); }
.status-badge { padding:4px 8px; border-radius:6px; font-size:11px; background:var(--surface-hover); }
[data-state="active"] .status-badge { color:var(--el-color-primary); background:var(--el-color-primary-light-9); }
[data-state="attention"] .status-badge { color:var(--el-color-warning); background:var(--el-color-warning-light-9); }
[data-state="done"] .status-badge { color:var(--el-color-success); background:var(--el-color-success-light-9); }
.task-empty { display:flex; align-items:center; flex-direction:column; gap:12px; text-align:center; padding:64px 16px; color:var(--muted-foreground); font-size:13px; }
.task-empty p { margin:0; line-height:1.6; }
.panel-error { padding:12px; border:1px solid var(--border); border-radius:10px; font-size:13px; }
.panel-footer { margin:0; color:var(--muted-foreground); text-align:center; font-size:12px; }
:global(.generation-task-drawer.el-drawer) { background:var(--surface); color:var(--foreground); border-left:1px solid var(--border); }
:global(.generation-task-drawer .el-drawer__header) { margin:0; padding:24px; border-bottom:1px solid var(--border); }
:global(.generation-task-drawer .el-drawer__body) { padding:20px 24px; }
:global(.generation-task-drawer .el-drawer__footer) { padding:14px 24px; border-top:1px solid var(--border); }
@media(max-width:480px) { :global(.generation-task-drawer .el-drawer__header),:global(.generation-task-drawer .el-drawer__body) { padding:16px; } }
</style>
