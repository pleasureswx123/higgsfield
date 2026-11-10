<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useProviderCalls } from '@/composables/studio/useProviderCalls'
import { groupCallProcess, callTaskState, executionDuration, assetQueryStatus } from '@/utils/callProcess'
import { formatBusinessTime } from '@/utils/time'
import { creationInput } from '@/utils/creationInput'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const displayTime = value => formatBusinessTime(value, 'YYYY-MM-DD HH:mm:ss', 'Asia/Shanghai') || '—'
const callerLabel = row => row.callerName || row.callerUsername || (row.callerId ? `用户 ${row.callerId}` : '未记录')
const { allowed, filters, rows, page, total, loading, error, selectedId, detail, detailLoading, detailError, load, search, reset, inspect, close, view, processId, processRows, processLoading, processError, inspectProcess, closeProcess } = useProviderCalls()
const processOpen = computed({ get: () => !!processId.value, set: value => { if (!value) closeProcess() } })
const processGroups = computed(() => groupCallProcess(processRows.value))
const processTask = computed(() => view.value === 'tasks' ? rows.value.find(row => row.id === processId.value) : null)
const callIssue = call => call.state === 'unknown' || call.acceptance === 'rejected' || call.httpStatus >= 400
const expandedGroups = ref([])
function showProcess(id) { expandedGroups.value = []; inspectProcess(id) }
const timeRange = computed({
  get: () => filters.from && filters.to ? [filters.from, filters.to] : null,
  set: value => { filters.from = value?.[0] || ''; filters.to = value?.[1] || '' },
})
const open = computed({ get: () => !!selectedId.value, set: value => { if (!value) close() } })
const states = { planned: '计划中', sending: '发送中', completed: '调用完成', unknown: '结果未知' }
const tab = ref('request')
const readableInput = computed(() => creationInput(detail.value?.task))
const operations = { image: '图片生成', video_submit: '视频提交', video_poll: '视频状态查询', upload: '参考素材上传', register: '素材注册', asset_get: '检查参考素材', test: '模型测试' }
async function copyCurl(value) {
  try { await navigator.clipboard.writeText(value); ElMessage.success('已复制脱敏 cURL') }
  catch { ElMessage.warning('复制失败，请选中下方 cURL 手动复制') }
}
function showTask(id) {
  close()
  showProcess(id)
}
const acceptance = { accepted: '已受理', rejected: '未受理', unknown: '受理未知', not_applicable: '不适用' }
</script>
<template>
  <div class="app-container">
    <header><h2>调用记录</h2><el-button text @click="settings.toggleTheme()">切换主题</el-button></header>
    <p>先查看任务结果，再进入执行过程排查。一个任务可包含素材准备、生成提交和多次进度查询；调用次数不代表生成次数或收费次数。</p>
    <el-radio-group v-model="view" class="view-switch"><el-radio-button value="tasks">任务概览</el-radio-button><el-radio-button value="calls">全部调用明细</el-radio-button></el-radio-group>
    <p v-if="view === 'tasks'">每个有调用记录的生成任务显示一行。筛选按调用记录匹配任务，调用次数和执行过程始终展示该任务全部记录。供应商生成成功不等于结果已归档。</p>
    <el-alert v-if="!allowed" title="没有运行治理查询权限" type="warning" :closable="false" />
    <el-form inline @submit.prevent>
      <el-form-item label="任务编号"><el-input v-model="filters.jobId" maxlength="19" clearable /></el-form-item>
      <el-form-item label="供应商账号ID"><el-input v-model="filters.accountId" maxlength="19" clearable /></el-form-item>
      <el-form-item label="调用状态"><el-select v-model="filters.state" clearable style="width:160px"><el-option v-for="(label,value) in states" :key="value" :label="label" :value="value" /></el-select></el-form-item>
      <el-form-item label="记录创建时间（上海）"><el-date-picker v-model="timeRange" type="datetimerange" value-format="YYYY-MM-DD HH:mm:ss" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" clearable /></el-form-item>
      <el-form-item><el-button :disabled="!allowed" :loading="loading" @click="search">查询</el-button><el-button :disabled="!allowed" @click="reset">重置</el-button></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-if="view === 'tasks'" v-loading="loading" :data="rows" empty-text="暂无匹配的任务">
      <el-table-column prop="id" label="任务编号" width="100" />
      <el-table-column prop="projectId" label="项目编号" width="100" />
      <el-table-column label="发起人" min-width="150"><template #default="{row}"><div>{{ callerLabel(row) }}</div><div class="caller-account">{{ row.callerUsername }}</div></template></el-table-column>
      <el-table-column label="生成类型" width="95"><template #default="{row}">{{ ({image:'图片',video:'视频',chat:'对话'})[row.kind] || row.kind }}</template></el-table-column>
      <el-table-column label="生成状态" min-width="160"><template #default="{row}">{{ callTaskState(row) }}</template></el-table-column>
      <el-table-column label="调用情况" min-width="140"><template #default="{row}"><div>{{ row.callCount }} 次调用</div><div class="caller-account">其中进度查询 {{ row.pollCount }} 次</div></template></el-table-column>
      <el-table-column label="创建时间（上海）" width="185"><template #default="{row}">{{ displayTime(row.createdAt) }}</template></el-table-column>
      <el-table-column label="生成执行耗时" width="145"><template #default="{row}">{{ executionDuration(row) }}</template></el-table-column>
      <el-table-column label="操作" fixed="right" width="125"><template #default="{row}"><el-button text @click="showProcess(row.id)">查看执行过程</el-button></template></el-table-column>
    </el-table>
    <el-table v-else v-loading="loading" :data="rows" empty-text="暂无可查看的调用记录">
      <el-table-column prop="id" label="调用ID" min-width="120" />
      <el-table-column prop="jobId" label="任务编号" min-width="120" />
      <el-table-column label="调用人" min-width="170"><template #default="{row}"><div>{{ callerLabel(row) }}</div><div v-if="row.callerUsername" class="caller-account">{{ row.callerUsername }}</div></template></el-table-column>
      <el-table-column label="操作" min-width="120"><template #default="{row}">{{ operations[row.operation] || row.operation }}<div v-if="row.assetQuery" class="caller-account">{{ row.assetQuery.name }}</div></template></el-table-column>
      <el-table-column label="调用状态" min-width="120"><template #default="{row}">{{ states[row.state] }}</template></el-table-column>
      <el-table-column label="受理／素材状态" min-width="120"><template #default="{row}">{{ row.assetQuery ? assetQueryStatus(row) : acceptance[row.acceptance] }}</template></el-table-column>
      <el-table-column prop="httpStatus" label="HTTP状态" width="110" />
      <el-table-column v-if="rows.some(row => row.businessCode)" prop="businessCode" label="业务码" min-width="120" />
      <el-table-column label="开始发送（上海）" width="185"><template #default="{row}">{{ displayTime(row.startedAt) }}</template></el-table-column>
      <el-table-column label="记录结束（上海）" width="185"><template #default="{row}">{{ displayTime(row.finishedAt) }}</template></el-table-column>
      <el-table-column label="操作" fixed="right" width="220"><template #default="{row}"><div class="call-actions"><el-button text @click="inspect(row.id)">查看详情</el-button><el-button v-if="row.jobId && String(row.jobId) !== filters.jobId.trim()" text @click="showTask(row.jobId)">查看任务全部调用</el-button></div></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load" />
    <el-drawer v-model="processOpen" :title="`任务 ${processId} · 执行过程`" size="min(850px, 95vw)" append-to-body destroy-on-close>
      <div v-loading="processLoading">
        <el-alert v-if="processTask" :title="`${callTaskState(processTask)} · 生成执行耗时 ${executionDuration(processTask)}`" :type="processTask.upstreamState === '4' ? 'error' : 'info'" :closable="false" />
        <p>按发生时间排列，共 {{ processRows.length }} 次调用。连续进度查询默认折叠；查看详情只读取已保存证据，不会重新生成。</p>
        <p>这里展示供应商调用过程；生成执行耗时不包含后续归档与费用结算。调用完成仅表示本次接口请求结束。</p>
        <el-alert v-if="processError" :title="processError" type="error" :closable="false" />
        <el-button :loading="processLoading" @click="showProcess(processId)">刷新执行过程</el-button>
        <el-timeline class="exchange-timeline">
          <el-timeline-item v-for="group in processGroups" :key="group.id" :timestamp="displayTime(group.calls[0].startedAt)" placement="top">
            <template v-if="group.operation === 'video_poll'">
              <el-collapse v-model="expandedGroups"><el-collapse-item :name="group.id" :title="`等待生成 · 进度查询 ${group.calls.length} 次（展开查看）`">
                <div v-for="call in group.calls" :key="call.id" class="process-call">
                  <span>调用 {{ call.id }} · {{ displayTime(call.startedAt) }} · {{ states[call.state] }} · HTTP {{ call.httpStatus ?? '未记录' }}</span>
                  <el-button text @click="inspect(call.id)">查看调用详情</el-button>
                </div>
              </el-collapse-item></el-collapse>
              <p>最近查询：{{ displayTime(group.calls.at(-1).finishedAt) }}；结果以任务生成状态为准。</p>
              <el-alert v-if="group.calls.some(callIssue)" :title="`其中 ${group.calls.filter(callIssue).length} 次查询异常或结果未知，请展开查看。`" type="warning" :closable="false" />
            </template>
            <template v-else>
              <h3>{{ operations[group.operation] || group.operation }}</h3>
              <p v-if="group.calls[0].assetQuery">{{ group.calls[0].assetQuery.name }}</p>
              <div class="process-call"><span>调用 {{ group.calls[0].id }} · {{ states[group.calls[0].state] }} · {{ group.calls[0].assetQuery ? assetQueryStatus(group.calls[0]) : acceptance[group.calls[0].acceptance] }}</span><el-button text @click="inspect(group.calls[0].id)">查看调用详情</el-button></div>
            </template>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
    <el-drawer v-model="open" title="调用详情 · 请求与返回" size="min(960px, 95vw)" append-to-body destroy-on-close>
      <div v-loading="detailLoading" class="evidence">
        <p>调用ID：{{ selectedId }}</p>
        <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
        <el-button v-if="detailError" text @click="inspect(selectedId)">重新读取</el-button>
        <template v-if="detail">
          <p v-if="detail.assetQuery">参考素材：{{ detail.assetQuery.name }}</p>
          <p v-if="detail.costCenterId">成本中心ID：{{ detail.costCenterId }}</p>
          <p v-if="detail.businessCode">供应商业务码：{{ detail.businessCode }}</p>
          <p>{{ operations[detail.operation] || detail.operation }} · {{ states[detail.state] }} · {{ detail.assetQuery ? assetQueryStatus(detail) : acceptance[detail.acceptance] }} · HTTP {{ detail.httpStatus ?? '未记录' }}</p>
          <el-button :loading="detailLoading" @click="inspect(selectedId)">刷新详情</el-button>
          <el-button v-if="detail.jobId && String(detail.jobId) !== filters.jobId.trim() && String(detail.jobId) !== processId" @click="showTask(detail.jobId)">查看任务全部调用</el-button>
          <el-collapse v-if="detail.task"><el-collapse-item title="任务概况与创作输入" name="task">
            <p>任务编号 {{ detail.task.id }} · 项目编号 {{ detail.task.projectId }} · 发起人 {{ callerLabel(detail) }}</p>
            <p>创建于 {{ displayTime(detail.task.createdAt) }}（上海） · {{ ({'0':'已受理','1':'准备中','2':'提交中','3':'提交结果未知','4':'执行中','5':'已结束','6':'已阻塞'})[detail.task.orchestrationState] }}</p>
            <h3>提示词</h3>
            <div class="creation-prompt">{{ readableInput.prompt || '未记录提示词' }}</div>
            <h3>引用素材</h3>
            <ul v-if="readableInput.references.length" class="creation-references"><li v-for="item in readableInput.references" :key="item.index"><span>{{ item.name }}</span><el-tag size="small" type="info">{{ item.role }}</el-tag></li></ul>
            <p v-else>未记录引用素材</p>
            <h3>生成参数</h3>
            <dl v-if="readableInput.parameters.length" class="creation-parameters"><div v-for="item in readableInput.parameters" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
            <p v-else>未记录生成参数</p>
            <el-collapse><el-collapse-item title="原始输入数据（排查用）" name="raw-input"><p>模型版本 {{ detail.task.modelVersionId }}；以下为提交时保存的输入，非本次供应商请求正文。</p><pre>{{ JSON.stringify(detail.task.input, null, 2) }}</pre></el-collapse-item></el-collapse>
          </el-collapse-item></el-collapse>
          <p>密钥、媒体地址及大段媒体内容已脱敏或省略。cURL 为 Bash 格式，包含占位符，仅供排查；手动执行会产生新的请求。</p>
          <el-alert v-if="!detail.exchanges?.length" :title="detail.operation === 'test' ? '模型测试请到「供应商与模型」的测试详情查看 Request / Response。本页展示该调用的运行元数据。' : '此历史调用未保存本页可展示的请求与响应快照，不能还原实际 cURL。下方仅展示已留存的元数据。'" type="info" :closable="false" />
          <el-timeline v-else class="exchange-timeline">
            <el-timeline-item v-for="exchange in detail.exchanges" :key="exchange.id" :timestamp="`${displayTime(exchange.startedAt)}（上海）`" placement="top">
              <h3>{{ exchange.request.method }} {{ exchange.request.url }}</h3>
              <p>{{ exchange.finishedAt ? `记录结束：${displayTime(exchange.finishedAt)}（上海）` : '已保存发送意图，尚未记录返回；不代表供应商未受理' }}</p>
              <el-tabs v-model="tab">
                <el-tab-pane label="Request 请求参数" name="request"><pre>{{ JSON.stringify(exchange.request, null, 2) }}</pre></el-tab-pane>
                <el-tab-pane label="cURL" name="curl"><template v-if="exchange.curl"><el-button @click="copyCurl(exchange.curl)">复制脱敏 cURL</el-button><pre>{{ exchange.curl }}</pre></template><p v-else>此请求为文件流上传，文件正文未保存为命令，不能提供可重放的 cURL。</p></el-tab-pane>
                <el-tab-pane label="Response 返回情况" name="response">
                  <p v-if="!exchange.finishedAt">尚未记录响应，请稍后刷新。</p>
                  <template v-else>
                    <p>HTTP：{{ exchange.httpStatus ?? '未收到' }} · {{ ({response:'已收到 HTTP 响应',timeout:'请求超时',network_error:'网络异常'})[exchange.transport] || exchange.transport }}</p>
                    <p v-if="exchange.issue">调用诊断：{{ exchange.issue }}</p>
                    <p v-if="exchange.diagnostic?.phase === 'complete'">响应接收完成 · 已接收 {{ exchange.diagnostic.receivedBytes }} 字节</p>
                    <p v-else-if="exchange.diagnostic">失败阶段：{{ exchange.diagnostic.phase === 'response_body' ? '接收响应正文' : '发送请求或等待响应头' }} · 异常类型：{{ exchange.diagnostic.exceptionType || '未记录' }} · 已接收 {{ exchange.diagnostic.receivedBytes }} 字节</p>
                    <pre v-if="exchange.diagnostic">{{ JSON.stringify(exchange.diagnostic, null, 2) }}</pre>
                    <pre v-if="exchange.response !== null">{{ JSON.stringify(exchange.response, null, 2) }}</pre>
                    <p v-else>{{ exchange.transport === 'response' ? '未取得可展示的 JSON 正文，请查看响应解析提示。' : '未收到响应正文，不能据此判断供应商未执行。' }}</p>
                  </template>
                </el-tab-pane>
              </el-tabs>
            </el-timeline-item>
          </el-timeline>
          <el-collapse><el-collapse-item title="其他调用元数据" name="metadata"><h3>请求元数据</h3><pre>{{ JSON.stringify(detail.requestMetadata, null, 2) }}</pre><h3>响应元数据</h3><pre>{{ JSON.stringify(detail.responseMetadata, null, 2) }}</pre></el-collapse-item></el-collapse>
        </template>
      </div>
    </el-drawer>
  </div>
</template>
<style scoped>
.view-switch { margin-bottom:16px; }
.process-call { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; padding:8px 0; }
.caller-account { color:var(--el-text-color-secondary); font-size:12px; }
.call-actions { display:flex; align-items:center; gap:8px; white-space:nowrap; }
.call-actions :deep(.el-button) { margin:0; padding:4px 0; }
.exchange-timeline { margin-top:24px; padding-left:8px; }
h3 { overflow-wrap:anywhere; }
header { display:flex; align-items:center; justify-content:space-between; }
p { color:var(--el-text-color-secondary); }
.el-pagination { margin-top:20px; }
.evidence { min-height:100px; }
.creation-prompt { white-space:pre-wrap; overflow-wrap:anywhere; max-height:280px; overflow:auto; padding:12px; border:1px solid var(--el-border-color); border-radius:6px; background:var(--el-fill-color-light); color:var(--el-text-color-primary); }
.creation-references { list-style:none; padding:0; }
.creation-references li { display:flex; align-items:center; gap:12px; padding:6px 0; overflow-wrap:anywhere; }
.creation-parameters { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
.creation-parameters > div { display:flex; gap:12px; }
.creation-parameters dt { color:var(--el-text-color-secondary); }
.creation-parameters dd { margin:0; overflow-wrap:anywhere; }
pre { padding:16px; background:var(--el-fill-color-light); color:var(--el-text-color-primary); border:1px solid var(--el-border-color); border-radius:6px; white-space:pre-wrap; overflow-wrap:anywhere; max-height:45vh; overflow:auto; }
</style>
