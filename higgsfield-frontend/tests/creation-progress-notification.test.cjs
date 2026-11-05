const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const compile = file => ts.transpileModule(readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const feedback = {}
runInNewContext(compile('src/utils/generationFeedback.ts'), { exports: feedback, Date })
test('多个已发送任务分别通知，刷新不重复通知，首次加载不弹历史结果', async () => {
 const notifications = [], hooks = {}, exports = {}
 const row = (id, state = 'submitting') => ({ id, projectId: '2', kind: 'image', promptExcerpt: `图片${id}`, createTime: new Date().toISOString(), orchestrationState: state, upstreamState: 'running', requestState: 'awaiting_response', archiveSummary: { ready: state === 'finished' ? 1 : 0, pending: 0, failed: 0 } })
 let rows = [row('1'), row('2'), row('3', 'finished')]
 runInNewContext(compile('src/composables/useCreationProgress.ts'), { exports, AbortController, Date, setTimeout: () => 1, clearTimeout() {}, require(id) {
   if (id === 'vue') return { ...vue, onActivated: fn => hooks.activate = fn, onDeactivated: fn => hooks.deactivate = fn, onBeforeUnmount: fn => hooks.unmount = fn }
   if (id === 'element-plus') return { ElNotification: value => notifications.push(value) }
   if (id === '@/utils/generationFeedback') return feedback
   if (id === '@/stores/auth') return { useAuthStore: () => ({ token: 'token' }) }
   if (id === '@/api/generations') return { listGenerations: async query => { assert.equal(query.category, 'active'); return { rows: structuredClone(rows.filter(row => !['finished', 'submission_unknown'].includes(row.orchestrationState))), hasNext: false } }, getGeneration: async id => ({ data: structuredClone(rows.find(row => row.id === id)) }) }
   throw Error(id)
 } })
 const opened = [], scope = vue.effectScope()
 const state = scope.run(() => exports.useCreationProgress(() => '2', () => null, () => undefined, () => {}, id => opened.push(id)))
 await new Promise(resolve => setImmediate(resolve))
 assert.equal(notifications.length, 0)
 rows = [row('1', 'finished'), row('2', 'submission_unknown'), row('3', 'finished')]
 await state.reload()
 assert.equal(notifications.length, 2)
 notifications[0].onClick(); assert.deepEqual(opened, ['1'])
 await state.reload(); assert.equal(notifications.length, 2)
 hooks.unmount(); scope.stop()
})
