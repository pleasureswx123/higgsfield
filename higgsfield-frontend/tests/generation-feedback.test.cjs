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

test('请求发出后立即释放按钮，下一张不等待上一张结果', () => {
 const { generationSubmissionFeedback: button } = exportsObject
 assert.equal(button(base).busy, true)
 assert.equal(button({ ...base, executionStage: 'worker_claimed' }).label, '后台已领取')
 assert.equal(button({ ...base, orchestrationState: 'preparing', executionStage: 'references_preparing' }).label, '准备参考图…')
 assert.equal(button({ ...base, orchestrationState: 'submitting', requestState: 'preparing_request' }).busy, true)
 for (const requestState of ['awaiting_response', 'response_received', 'transport_error']) {
   assert.equal(button({ ...base, orchestrationState: 'submitting', requestState }).busy, false)
 }
 assert.equal(button({ ...base, orchestrationState: 'submission_unknown' }).busy, false)
 assert.equal(button({ ...base, orchestrationState: 'accepted' }).busy, true)
})
