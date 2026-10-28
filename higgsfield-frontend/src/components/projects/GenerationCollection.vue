<script setup lang="ts">
import { onDeactivated, ref, watch } from 'vue'
import GenerationDetail from './GenerationDetail.vue'
import GenerationCardBilling from './GenerationCardBilling.vue'
import GenerationCardMedia from './GenerationCardMedia.vue'
import ProjectFilter from './ProjectFilter.vue'
import type { Project } from '@/api/projects'
import { ElSelect, ElOption, ElPagination, ElForm, ElFormItem, ElDatePicker, type FormRules } from 'element-plus'
import { libraryWindow } from '@/utils/libraryWindow'
import Button from '@/components/ui/Button.vue'
import { useGenerations } from '@/composables/useGenerations'
import { formatProjectDate } from '@/utils/projects'
const props = withDefaults(defineProps<{ projectId?: string; active?: boolean }>(), {
  active: true,
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
const { rows, total, page, kind, state, dates, loading, error, refresh } = useGenerations(
  () => props.projectId,
  () => props.active,
  () => filteredProject.value?.id,
)
const kinds = { image: '图片', video: '视频', chat: '对话' }
const states = {
  accepted: '已受理',
  preparing: '准备中',
  submitting: '提交中',
  submission_unknown: '提交待核查',
  running: '执行中',
  finished: '编排结束',
  blocked: '已阻塞',
}
const upstream = {
  not_submitted: '未提交',
  queued: '排队中',
  running: '生成中',
  succeeded: '生成成功',
  failed: '生成失败',
  cancelled: '已取消',
  unknown: '待核查',
}
const billing = { pending: '待确认', calculated: '已计算', confirmed: '已确认', disputed: '有争议' }
const dateRules: FormRules = { dates: [{ trigger: 'change', validator: (_rule, value, callback) => {
  try { libraryWindow(value); callback() }
  catch (cause) { callback(cause instanceof Error ? cause : new Error('日期无效')) }
} }] }
</script>
<template>
  <section class="generation-collection" aria-label="生成任务记录">
    <div class="generation-toolbar">
      <ProjectFilter v-if="!projectId" v-model="filteredProject" :active="active" />
      <ElSelect v-model="kind" aria-label="生成类型" placeholder="全部类型"
        ><ElOption label="全部类型" value="" /><ElOption
          v-for="(label, value) in kinds"
          :key="value"
          :label="label"
          :value="value"
      /></ElSelect>
      <ElSelect v-model="state" aria-label="任务阶段" placeholder="全部阶段"
        ><ElOption label="全部阶段" value="" /><ElOption
          v-for="(label, value) in states"
          :key="value"
          :label="label"
          :value="value"
      /></ElSelect>
      <Button variant="ghost" :disabled="loading" @click="refresh">刷新</Button>
    </div>
    <ElForm :model="{ dates }" :rules="dateRules" label-position="top" @submit.prevent>
      <ElFormItem label="任务创建日期（上海时间，包含结束日）" prop="dates">
        <ElDatePicker v-model="dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" clearable />
      </ElFormItem>
    </ElForm>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-else-if="loading" role="status">正在加载生成记录…</p>
    <div v-else-if="!rows.length" class="generation-empty">
      当前范围暂无符合筛选条件的生成记录。
    </div>
    <div v-else class="generation-grid">
      <article v-for="row in rows" :key="row.id" class="generation-card">
        <GenerationCardMedia v-if="row.cardPreview" :preview="row.cardPreview" />
        <header>
          <strong>{{ kinds[row.kind] }} · {{ row.id }}</strong
          ><span>{{ states[row.orchestrationState] }}</span>
        </header>
        <p class="muted">{{ formatProjectDate(row.createTime) }}</p>
        <p class="muted">所属项目：{{ row.projectName || `项目 #${row.projectId}` }}</p>
        <dl>
          <div>
            <dt>上游生成</dt>
            <dd>{{ upstream[row.upstreamState] }}</dd>
          </div>
          <div>
            <dt>输出归档</dt>
            <dd v-if="row.archiveSummary.total">
              共 {{ row.archiveSummary.total }} · 就绪 {{ row.archiveSummary.ready }} · 待归档
              {{ row.archiveSummary.pending }} · 失败 {{ row.archiveSummary.failed }}
            </dd>
            <dd v-else>尚无输出记录</dd>
          </div>
          <div>
            <dt>费用状态</dt>
            <dd>{{ billing[row.billingState] }}</dd>
          </div>
          <div><dt>平台费用</dt><dd><GenerationCardBilling :task="row" /></dd></div>
        </dl>
        <Button variant="ghost" @click="selected = row.id">查看详情</Button>
        <RouterLink
          v-if="!projectId"
          :to="{
            name: 'project-detail',
            params: { id: row.projectId },
            query: { tab: 'generations' },
          }"
          class="text-button"
          >查看所属项目</RouterLink
        >
      </article>
    </div>
    <ElPagination
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
.generation-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
}
.generation-toolbar .el-select {
  width: 190px;
}
.generation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 350px), 1fr));
  gap: 18px;
}
.generation-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
}
.generation-card header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
}
.generation-card header span {
  color: var(--muted-foreground);
  font-size: 13px;
}
.generation-card dl {
  display: grid;
  gap: 12px;
  font-size: 13px;
}
.generation-card dl div {
  display: grid;
  grid-template-columns: 70px 1fr;
  gap: 12px;
}
.generation-card dt {
  color: var(--muted-foreground);
}
.generation-card dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.generation-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--muted-foreground);
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: 16px;
}
.el-pagination {
  margin-top: 24px;
}
</style>
