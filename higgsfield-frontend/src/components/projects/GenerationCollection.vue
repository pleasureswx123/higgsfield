<script setup lang="ts">
import { useTimestamp, useIntervalFn } from '@vueuse/core'
import { generationFeedback } from '@/utils/generationFeedback'
const feedbackNow = useTimestamp({ scheduler: callback => useIntervalFn(callback, 1000) })
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import StudioSelect from '@/components/ui/StudioSelect.vue'
import StudioPagination from '@/components/ui/StudioPagination.vue'
import { onDeactivated, ref, watch } from 'vue'
import GenerationDetail from './GenerationDetail.vue'
import { Table, TableHeader, TableHead, TableBody, TableRow, TableCell } from '@/components/ui/table'
import { IconPhoto, IconVideo, IconMessage } from '@tabler/icons-vue'
import type { GenerationSummary } from '@/api/generations'
import GenerationCardMedia from './GenerationCardMedia.vue'
import ProjectFilter from './ProjectFilter.vue'
import type { Project } from '@/api/projects'
import { ElForm, ElFormItem, ElDatePicker, type FormRules } from 'element-plus'
import { libraryWindow } from '@/utils/libraryWindow'
import Button from '@/components/ui/Button.vue'
import { useGenerations } from '@/composables/useGenerations'
import { formatProjectDate } from '@/utils/projects'
const props = withDefaults(defineProps<{ projectId?: string; active?: boolean; refreshKey?: number }>(), {
  active: true,
  refreshKey: 0,
  projectId: undefined,
})
const selected = ref<string>()
const filteredProject = ref<Project | null>(null)
onDeactivated(() => {
  selected.value = undefined
})
watch(
  () => [props.projectId, props.active, filteredProject.value?.id],
  () => {
    selected.value = undefined
  },
)
const { rows, total, page, kind, state, category, dates, loading, error, refresh } = useGenerations(
  () => props.projectId,
  () => props.active,
  () => filteredProject.value?.id,
)
watch(() => props.refreshKey, () => { if (props.active) void refresh() })
const kinds = { image: '图片', video: '视频', chat: '对话' }
const states = {
  accepted: '等待启动',
  preparing: '准备素材中',
  submitting: '提交中',
  submission_unknown: '提交异常',
  running: '执行中',
  finished: '已结束',
  blocked: '已阻塞',
}
function taskStatus(row: GenerationSummary) {
  return generationFeedback(row, feedbackNow.value)
}
function resultLabel(row: GenerationSummary) {
  if (row.archiveSummary.ready) return `${row.archiveSummary.ready} ${row.kind === 'image' ? '张图片' : row.kind === 'video' ? '个视频' : '条结果'}`
  if (row.orchestrationState === 'submission_unknown') return '暂无结果'
  if (row.archiveSummary.failed) return '保存未完成'
  if (row.archiveSummary.pending) return '正在保存'
  return '暂无结果'
}
function actionLabel(row: GenerationSummary) {
  if (row.archiveSummary.ready) return '查看结果'
  return row.orchestrationState === 'submission_unknown' || row.upstreamState === 'failed' || row.orchestrationState === 'blocked' || row.archiveSummary.failed ? '查看原因' : '查看详情'
}
const dateRules: FormRules = { dates: [{ trigger: 'change', validator: (_rule, value, callback) => {
  try { libraryWindow(value); callback() }
  catch (cause) { callback(cause instanceof Error ? cause : new Error('日期无效')) }
} }] }
</script>
<template>
  <section class="generation-collection" aria-label="生成任务记录">
    <div v-if="projectId" class="project-page-heading"><div><h2>项目生成记录</h2><p class="muted">查看当前项目团队的 AI 生成任务与结果，显示范围由项目权限决定。</p></div></div>
    <Tabs v-model="category" class="generation-status-tabs">
      <TabsList class="studio-tabs studio-pill-tabs" aria-label="生成状态"><TabsTrigger value="">全部</TabsTrigger><TabsTrigger value="active">进行中</TabsTrigger><TabsTrigger value="attention">异常</TabsTrigger><TabsTrigger value="done">已结束</TabsTrigger></TabsList>
    </Tabs>
    <div class="generation-toolbar">
      <ProjectFilter v-if="!projectId" v-model="filteredProject" :active="active" />
      <StudioSelect v-model="kind" aria-label="生成类型" placeholder="全部类型"
         :options="[{ label: '全部类型', value: '' }, ...Object.entries(kinds).map(([value, label]) => ({ value, label }))]" />
      <StudioSelect v-model="state" aria-label="任务阶段" placeholder="全部阶段"
         :options="[{ label: '全部阶段', value: '' }, ...Object.entries(states).map(([value, label]) => ({ value, label }))]" />
      <ElForm class="generation-date-filter" :model="{ dates }" :rules="dateRules" title="任务创建日期，按上海时间筛选，包含结束日" @submit.prevent>
        <ElFormItem prop="dates">
          <ElDatePicker v-model="dates" aria-label="任务创建日期范围（上海时间，包含结束日）" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" clearable />
        </ElFormItem>
      </ElForm>
      <Button variant="ghost" :disabled="loading" @click="refresh">刷新</Button>
    </div>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-else-if="loading" role="status">正在加载生成记录…</p>
    <div v-else-if="!rows.length" class="generation-empty">
      当前范围暂无符合筛选条件的生成记录。
    </div>
    <div v-else class="generation-table-shell">
      <Table class="generation-table" aria-label="生成记录列表">
        <TableHeader><TableRow>
          <TableHead class="content-column">生成内容</TableHead><TableHead>状态</TableHead><TableHead>结果</TableHead><TableHead>创建时间</TableHead><TableHead class="action-column">操作</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          <TableRow v-for="row in rows" :key="row.id">
            <TableCell class="content-column">
              <div class="generation-content">
                <div class="generation-thumbnail">
                  <GenerationCardMedia v-if="row.cardPreview?.kind === 'image'" :preview="row.cardPreview" />
                  <IconVideo v-else-if="row.kind === 'video'" :size="22" aria-hidden="true" />
                  <IconMessage v-else-if="row.kind === 'chat'" :size="22" aria-hidden="true" />
                  <IconPhoto v-else :size="22" aria-hidden="true" />
                </div>
                <div class="generation-description">
                  <button type="button" class="generation-prompt" :title="row.promptExcerpt || '未提供提示词'" @click="selected = row.id">{{ row.promptExcerpt || '未提供提示词' }}</button>
                  <div class="generation-subtitle"><span>{{ kinds[row.kind] }}</span><RouterLink v-if="!projectId" :to="{ name: 'project-detail', params: { id: row.projectId }, query: { tab: 'generations' } }">{{ row.projectName || '查看所属项目' }}</RouterLink></div>
                </div>
              </div>
            </TableCell>
            <TableCell><span class="generation-status" :data-tone="taskStatus(row).tone"><span aria-hidden="true">●</span>{{ taskStatus(row).label }}</span></TableCell>
            <TableCell class="result-column">{{ resultLabel(row) }}</TableCell>
            <TableCell class="date-column">{{ formatProjectDate(row.createTime) }}</TableCell>
            <TableCell class="action-column"><Button variant="ghost" :aria-label="`${actionLabel(row)}：${row.promptExcerpt || kinds[row.kind]}`" @click="selected = row.id">{{ actionLabel(row) }}</Button></TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
    <StudioPagination
      v-if="total > 20"
      v-model:current-page="page"
      :page-size="20"
      :total="total"
      layout="total, prev, pager, next"
    />
    <GenerationDetail v-model="selected" />
  </section>
</template>
<style scoped>
.generation-status-tabs { margin-bottom:16px; }
.generation-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
}
.generation-toolbar :deep(.studio-select) {
  width: 190px;
}
.generation-date-filter {
  flex: 0 1 320px;
  min-width: 0;
  max-width: 100%;
}
.generation-date-filter :deep(.el-form-item) { margin-bottom: 0; }
.generation-date-filter :deep(.el-date-editor) { width: 100%; min-width: 0; }
.generation-table-shell { border:1px solid var(--border); border-radius:12px; overflow:hidden; background:var(--surface); }
.generation-table-shell :deep(table) { width:100%; min-width:760px; table-layout:fixed; font-size:12px; }
.generation-table-shell :deep(th) { height:40px; padding:0 16px; color:var(--muted-foreground); font-size:12px; font-weight:500; background:var(--surface-raised); }
.generation-table-shell :deep(td) { height:80px; padding:12px 16px; border-top:1px solid var(--border); vertical-align:middle; }
.generation-table-shell :deep(tbody tr:hover) { background:var(--surface-hover); }
.generation-table-shell :deep(.content-column) { width:43%; }
.generation-table-shell :deep(.date-column) { color:var(--muted-foreground); font-size:12px; }
.generation-table-shell :deep(th:nth-child(4)) { width:190px; }
.generation-table-shell :deep(.action-column) { width:106px; text-align:right; }
.generation-content { display:flex; align-items:center; gap:12px; min-width:0; }
.generation-thumbnail { display:flex; align-items:center; justify-content:center; width:52px; height:52px; flex:none; border-radius:8px; overflow:hidden; color:var(--muted-foreground); background:var(--surface-raised); }
.generation-thumbnail :deep(.generation-card-media) { width:52px; height:52px; aspect-ratio:1; margin:0; border-radius:0; font-size:10px; }
.generation-thumbnail :deep(img) { object-fit:cover; }
.generation-thumbnail :deep(button) { padding:2px; font-size:10px; }
.generation-description { min-width:0; }
.generation-prompt { display:block; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-align:left; border:0; padding:0; background:transparent; color:var(--foreground); font:inherit; font-weight:500; cursor:pointer; }
.generation-prompt:hover { text-decoration:underline; }
.generation-prompt:focus-visible { outline:2px solid var(--ring); outline-offset:3px; border-radius:2px; }
.generation-subtitle { display:flex; gap:8px; color:var(--muted-foreground); margin-top:5px; font-size:11px; }
.generation-status { display:inline-flex; align-items:center; gap:6px; white-space:nowrap; font-size:12px; }
.generation-status > span { font-size:8px; }
.generation-status[data-tone="success"] > span { color:var(--el-color-success); }
.generation-status[data-tone="danger"] > span { color:var(--el-color-danger); }
.generation-status[data-tone="warning"] > span { color:var(--el-color-warning); }
.generation-status[data-tone="progress"] > span { color:var(--el-color-primary); }
.generation-status[data-tone="neutral"], .result-column { color:var(--muted-foreground); }
.generation-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--muted-foreground);
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: 16px;
}
.studio-pagination {
  margin-top: 24px;
}
</style>
