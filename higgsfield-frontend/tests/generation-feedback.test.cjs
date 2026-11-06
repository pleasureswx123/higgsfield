const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const exportsObject = {}
runInNewContext(ts.transpileModule(readFileSync('src/utils/generationFeedback.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: exportsObject, Date })
const { generationFeedback } = exportsObject
const base = { createTime: '2026-11-04T10:00:00Z', orchestrationState: 'accepted', upstreamState: 'not_submitted', archiveSummary: { total: 0, ready: 0, failed: 0, pending: 0 } }
test('平台接收不等于供应商生成，超时不伪造失败并停止无限转圈', () => {
 const queued = generationFeedback(base, Date.parse(base.createTime) + 1000)
 assert.equal(queued.label, '等待启动'); assert.equal(queued.busy, true)
 const delayed = generationFeedback(base, Date.parse(base.createTime) + 120000)
 assert.equal(delayed.label, '请求尚未发出'); assert.equal(delayed.busy, true); assert.equal(delayed.spinning, false)
 assert.match(delayed.description, /尚未向生成服务发送请求/)
 assert.doesNotMatch(delayed.description, /联系管理员/)
 assert.equal(base.orchestrationState, 'accepted')
})
test('生成、保存和完成分开显示；未知结果继续防重复提交', () => {
 assert.equal(generationFeedback({ ...base, orchestrationState: 'running', upstreamState: 'running' }).label, '生成中')
 assert.equal(generationFeedback({ ...base, orchestrationState: 'finished', upstreamState: 'succeeded', archiveSummary: { total: 1, ready: 0, failed: 0, pending: 1 } }).busy, true)
 assert.equal(generationFeedback({ ...base, orchestrationState: 'finished', upstreamState: 'succeeded', archiveSummary: { total: 1, ready: 1, failed: 0, pending: 0 } }).busy, false)
 assert.equal(generationFeedback({ ...base, orchestrationState: 'submission_unknown' }).busy, true)
 assert.equal(generationFeedback({ ...base, upstreamState: 'failed' }).label, '生成失败')
 assert.equal(generationFeedback({ ...base, orchestrationState: 'submitting', requestState: 'awaiting_response' }).label, '等待响应')
 assert.equal(generationFeedback({ ...base, orchestrationState: 'submission_unknown', requestState: 'transport_error' }).label, '通信异常')
})

test('受理后按钮恢复，排队准备生成均不锁住创作入口', () => {
 const { generationSubmissionFeedback: button } = exportsObject
 for (const state of ['accepted', 'preparing', 'submitting', 'running', 'submission_unknown', 'finished']) {
  const result = button({ ...base, orchestrationState: state })
  assert.equal(result.busy, false); assert.equal(result.spinning, false)
 }
})
test('供应商名额与未知占用有明确原因且不持续转圈', () => {
 const full = generationFeedback({ ...base, queueReason: 'capacity_full' })
 assert.equal(full.label, '等待生成名额'); assert.equal(full.spinning, false)
 const unknown = generationFeedback({ ...base, queueReason: 'capacity_unknown' })
 assert.equal(unknown.label, '排队受阻'); assert.equal(unknown.busy, false)
 assert.match(unknown.description, /结果待核查/)
})
