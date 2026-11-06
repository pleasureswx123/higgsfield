<script setup lang="ts">
import type { GenerationSnapshot } from '@/api/generations'
import { formatProjectDate } from '@/utils/projects'
defineProps<{ execution: NonNullable<GenerationSnapshot['execution']> }>()
const operations: Record<string, string> = { image: '图片生成', video_submit: '视频生成', video_poll: '查询视频状态', upload: '上传参考素材', register: '注册参考素材', asset_get: '查询参考素材' }
const acceptance: Record<string, string> = { accepted: '供应商已受理', rejected: '供应商已拒绝', unknown: '结果未确认', not_applicable: '无需受理判断' }
const transport: Record<string, string> = { timeout: '等待响应超时', network_error: '网络连接异常', response: '已收到响应' }
function duration(value: number) { return value < 1000 ? `${value.toFixed(0)} ms` : `${(value / 1000).toFixed(2)} 秒` }
const phases: Record<string, string> = { 'connection.connect_tcp': '建立连接', 'connection.start_tls': '安全握手', 'send_request_headers': '发送请求头', 'send_request_body': '发送请求体', 'receive_response_headers': '等待响应头', 'receive_response_body': '接收响应正文', total: '调用总耗时' }
function phaseName(key: string) { return phases[key] || phases[key.replace(/^http(11|2)\./, '')] }
function time(value: string | null) {
  if (!value) return '尚未记录'
  return `${formatProjectDate(value)}:${new Date(value).getSeconds().toString().padStart(2, '0')}`
}
</script>
<template>
  <section class="execution-trace" aria-label="生成执行过程">
    <h3>执行过程</h3>
    <p v-if="execution.attemptCount === 0" class="trace-warning">任务已保存，后台尚未领取；供应商请求尚未发出。</p>
    <ol>
      <li v-for="event in execution.events" :key="event.id"><span>{{ event.label }}</span><time>{{ time(event.time) }}<small v-if="event.sincePreviousMs != null">距上一节点 {{ duration(event.sincePreviousMs) }}</small></time></li>
    </ol>
    <p v-if="!execution.calls.length" class="muted">暂无供应商调用，尚无 HTTP 状态和响应内容。</p>
    <details v-for="call in execution.calls" :key="call.id" class="call-evidence">
      <summary>{{ operations[call.operation] || '供应商调用' }} · {{ call.httpStatus ? `HTTP ${call.httpStatus}` : call.finishedAt ? '未记录 HTTP 响应' : '等待响应' }}</summary>
      <p class="muted">{{ acceptance[call.acceptance] }} · 调用 {{ call.id }}</p>
      <p class="muted">开始：{{ time(call.startedAt) }}<br />结束：{{ time(call.finishedAt) }}</p>
      <p v-if="!call.exchanges.length" class="muted">未记录请求正文及响应正文，不能据此确认供应商已收到请求。</p>
      <div v-for="(exchange, index) in call.exchanges" :key="index">
        <p>{{ exchange.finishedAt ? transport[exchange.transport || ''] || '调用结束' : exchange.requestSentAt ? '请求已发送，等待响应' : '正在准备或发送请求' }}<span v-if="exchange.httpStatus"> · HTTP {{ exchange.httpStatus }}</span></p>
        <p v-if="exchange.diagnostic?.exceptionType === 'RemoteProtocolError'" class="trace-warning">连接在完整响应返回前中断，无法确认生成结果。</p>
        <p v-if="exchange.diagnostic?.exceptionType" class="muted">异常类型：{{ exchange.diagnostic.exceptionType }}<span v-if="exchange.diagnostic.receivedBytes != null"> · 已接收 {{ exchange.diagnostic.receivedBytes }} 字节</span></p>
        <p class="muted">请求发送完成：{{ time(exchange.requestSentAt || null) }}<br />响应正文接收完成：{{ time(exchange.responseBodyAt || null) }}</p>
        <dl v-if="exchange.timingsMs" class="trace-timings"><template v-for="(value, key) in exchange.timingsMs" :key="key"><div v-if="phaseName(key)"><dt>{{ phaseName(key) }}</dt><dd>{{ duration(value) }}</dd></div></template></dl>
        <p v-if="exchange.issue" class="muted">诊断代码：{{ exchange.issue }}</p>
        <p v-if="exchange.diagnostic?.failedPhase" class="trace-warning">失败环节：{{ phaseName(exchange.diagnostic.failedPhase) || exchange.diagnostic.failedPhase }}</p>
        <details v-if="exchange.diagnostic"><summary>网络诊断 · 错误码与响应头</summary><pre>{{ JSON.stringify(exchange.diagnostic, null, 2) }}</pre></details>
        <details><summary>Request · 实际请求（已脱敏）</summary><p v-if="exchange.requestBodyBytes != null">正文大小：{{ exchange.requestBodyBytes }} 字节</p><p v-if="exchange.requestBodySha256">正文 SHA-256：{{ exchange.requestBodySha256 }}</p><pre>{{ JSON.stringify(exchange.request, null, 2) }}</pre></details>
        <details><summary>Response · 实际响应（已脱敏）</summary><pre v-if="exchange.response != null">{{ JSON.stringify(exchange.response, null, 2) }}</pre><p v-else class="muted">尚未记录响应正文</p></details>
      </div>
    </details>
    <p v-if="execution.events.length >= 200 || execution.calls.length >= 20" class="muted">展示最近 200 个执行节点、20 次调用。</p>
  </section>
</template>
<style scoped>
.execution-trace { border-top:1px solid var(--border); margin-top:18px; padding:16px 0; font-size:12px; }
h3 { margin:0 0 12px; font-size:13px; }
ol { list-style:none; margin:0; padding:0; }
li { display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid var(--border); }
time,.muted { color:var(--muted-foreground); }
time small { display:block; text-align:right; margin-top:3px; }
time { flex-shrink:0; font-size:11px; }
.trace-warning { color:var(--el-color-warning); }
.call-evidence { margin-top:12px; padding:12px; border:1px solid var(--border); border-radius:8px; }
summary { cursor:pointer; }
.trace-timings > div { display:flex; justify-content:space-between; padding:4px 0; gap:12px; }
.trace-timings dt { color:var(--muted-foreground); }
.trace-timings dd { margin:0; font-variant-numeric:tabular-nums; }
details details { margin-top:12px; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:280px; overflow:auto; padding:12px; background:var(--surface); border-radius:6px; }
</style>
