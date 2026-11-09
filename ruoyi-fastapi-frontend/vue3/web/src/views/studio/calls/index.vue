<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useProviderCalls } from '@/composables/studio/useProviderCalls'
import { formatBusinessTime } from '@/utils/time'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const displayTime = value => formatBusinessTime(value, 'YYYY-MM-DD HH:mm:ss', 'Asia/Shanghai') || '—'
const callerLabel = row => row.callerName || row.callerUsername || (row.callerId ? `用户 ${row.callerId}` : '未记录')
const { allowed, filters, rows, page, total, loading, error, selectedId, detail, detailLoading, detailError, load, search, reset, inspect, close } = useProviderCalls()
const timeRange = computed({
  get: () => filters.from && filters.to ? [filters.from, filters.to] : null,
  set: value => { filters.from = value?.[0] || ''; filters.to = value?.[1] || '' },
})
const open = computed({ get: () => !!selectedId.value, set: value => { if (!value) close() } })
const states = { planned: '计划中', sending: '发送中', completed: '调用完成', unknown: '结果未知' }
const tab = ref('request')
const operations = { image: '图片生成', video_submit: '视频提交', video_poll: '视频状态查询', upload: '参考素材上传', register: '素材注册', asset_get: '素材查询', test: '模型测试' }
async function copyCurl(value) {
  try { await navigator.clipboard.writeText(value); ElMessage.success('已复制脱敏 cURL') }
  catch { ElMessage.warning('复制失败，请选中下方 cURL 手动复制') }
}
function showTask(id) {
  filters.jobId = id
  filters.accountId = ''; filters.state = ''; filters.from = ''; filters.to = ''
  search()
}
const acceptance = { accepted: '已受理', rejected: '未受理', unknown: '受理未知', not_applicable: '不适用' }
</script>
<template>
  <div class="app-container">
    <header><h2>调用记录</h2><el-button text @click="settings.toggleTheme()">切换主题</el-button></header>
    <p>查看生成任务实际发送的请求与返回。按任务查询可追踪生成、素材上传与视频状态查询；查看记录不会重新生成。</p>
    <el-alert v-if="filters.jobId" :title="`当前任务 ${filters.jobId} 的调用记录（新到旧，可翻页）`" type="info" :closable="false" />
    <el-alert v-if="!allowed" title="没有运行治理查询权限" type="warning" :closable="false" />
    <el-form inline @submit.prevent>
      <el-form-item label="任务编号"><el-input v-model="filters.jobId" maxlength="19" clearable /></el-form-item>
      <el-form-item label="供应商账号ID"><el-input v-model="filters.accountId" maxlength="19" clearable /></el-form-item>
      <el-form-item label="状态"><el-select v-model="filters.state" clearable style="width:160px"><el-option v-for="(label,value) in states" :key="value" :label="label" :value="value" /></el-select></el-form-item>
      <el-form-item label="记录创建时间（上海）"><el-date-picker v-model="timeRange" type="datetimerange" value-format="YYYY-MM-DD HH:mm:ss" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" clearable /></el-form-item>
      <el-form-item><el-button :disabled="!allowed" :loading="loading" @click="search">查询</el-button><el-button :disabled="!allowed" @click="reset">重置</el-button></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="rows" empty-text="暂无可查看的调用记录">
      <el-table-column prop="id" label="调用ID" min-width="120" />
      <el-table-column prop="jobId" label="任务编号" min-width="120" />
      <el-table-column label="调用人" min-width="170"><template #default="{row}"><div>{{ callerLabel(row) }}</div><div v-if="row.callerUsername" class="caller-account">{{ row.callerUsername }}</div></template></el-table-column>
      <el-table-column label="操作" min-width="120"><template #default="{row}">{{ operations[row.operation] || row.operation }}</template></el-table-column>
      <el-table-column label="调用状态" min-width="120"><template #default="{row}">{{ states[row.state] }}</template></el-table-column>
      <el-table-column label="受理事实" min-width="120"><template #default="{row}">{{ acceptance[row.acceptance] }}</template></el-table-column>
      <el-table-column prop="httpStatus" label="HTTP状态" width="110" />
      <el-table-column v-if="rows.some(row => row.businessCode)" prop="businessCode" label="业务码" min-width="120" />
      <el-table-column label="开始发送（上海）" width="185"><template #default="{row}">{{ displayTime(row.startedAt) }}</template></el-table-column>
      <el-table-column label="记录结束（上海）" width="185"><template #default="{row}">{{ displayTime(row.finishedAt) }}</template></el-table-column>
      <el-table-column label="操作" fixed="right" width="185"><template #default="{row}"><div class="call-actions"><el-button text @click="inspect(row.id)">查看详情</el-button><el-button v-if="row.jobId" text @click="showTask(row.jobId)">同任务记录</el-button></div></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="total, prev, pager, next" @current-change="load" />
    <el-drawer v-model="open" title="调用详情 · 请求与返回" size="min(960px, 95vw)" append-to-body destroy-on-close>
      <div v-loading="detailLoading" class="evidence">
        <p>调用ID：{{ selectedId }}</p>
        <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
        <el-button v-if="detailError" text @click="inspect(selectedId)">重新读取</el-button>
        <template v-if="detail">
          <p v-if="detail.costCenterId">成本中心ID：{{ detail.costCenterId }}</p>
          <p v-if="detail.businessCode">供应商业务码：{{ detail.businessCode }}</p>
          <p>{{ operations[detail.operation] || detail.operation }} · {{ states[detail.state] }} · {{ acceptance[detail.acceptance] }} · HTTP {{ detail.httpStatus ?? '未记录' }}</p>
          <el-button :loading="detailLoading" @click="inspect(selectedId)">刷新详情</el-button>
          <el-button v-if="detail.jobId" @click="showTask(detail.jobId)">查看此任务全部调用</el-button>
          <el-collapse v-if="detail.task"><el-collapse-item title="任务概况与创作输入" name="task">
            <p>项目 {{ detail.task.projectId }} · 调用人 {{ callerLabel(detail) }} · 模型版本 {{ detail.task.modelVersionId }}</p>
            <p>创建于 {{ displayTime(detail.task.createdAt) }}（上海） · {{ ({'0':'已受理','1':'准备中','2':'提交中','3':'提交结果未知','4':'执行中','5':'已结束','6':'已阻塞'})[detail.task.orchestrationState] }}</p>
            <pre>{{ JSON.stringify(detail.task.input, null, 2) }}</pre>
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
                    <p v-if="exchange.diagnostic">失败阶段：{{ exchange.diagnostic.phase === 'response_body' ? '接收响应正文' : '发送请求或等待响应头' }} · 异常类型：{{ exchange.diagnostic.exceptionType }} · 已接收 {{ exchange.diagnostic.receivedBytes }} 字节</p>
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
.caller-account { color:var(--el-text-color-secondary); font-size:12px; }
.call-actions { display:flex; align-items:center; gap:8px; white-space:nowrap; }
.call-actions :deep(.el-button) { margin:0; padding:4px 0; }
.exchange-timeline { margin-top:24px; padding-left:8px; }
h3 { overflow-wrap:anywhere; }
header { display:flex; align-items:center; justify-content:space-between; }
p { color:var(--el-text-color-secondary); }
.el-pagination { margin-top:20px; }
.evidence { min-height:100px; }
pre { padding:16px; background:var(--el-fill-color-light); color:var(--el-text-color-primary); border:1px solid var(--el-border-color); border-radius:6px; white-space:pre-wrap; overflow-wrap:anywhere; max-height:45vh; overflow:auto; }
</style>
