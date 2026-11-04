const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

test('目录查询包含视频，归档完成自动通知素材刷新', async () => {
  const exports = {}, calls = [], hooks = {}
  let ready = 0, refreshed = 0
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useCreationProgress.ts'), 'utf8')
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, Error, setTimeout: () => 1, clearTimeout: () => {},
    require: name => name === 'vue' ? { ...vue, onActivated: () => {}, onDeactivated: () => {}, onBeforeUnmount: fn => { hooks.close = fn } }
      : name === '@/stores/auth' ? { useAuthStore: () => ({ token: 'token' }) }
      : { listGenerations: async query => { calls.push(query); return { rows: [{ id: '7', kind: 'video', orchestrationState: 'finished', archiveSummary: { ready, failed: 0 } }] } } },
  })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useCreationProgress(() => '2', () => '5', () => undefined, () => { refreshed++ }))
  await Promise.resolve()
  assert.equal(calls[0].kind, undefined)
  assert.equal(calls[0].folderId, undefined)
  assert.equal(calls[0].projectId, '2')
  const before = refreshed
  ready = 1
  await state.reload()
  assert.equal(refreshed, before + 1)
  assert.equal(state.label(state.rows.value[0]), '已保存 1 个视频')
  await state.reload()
  assert.equal(refreshed, before + 1)
  hooks.close()
  scope.stop()
})


test('生成与待确认分开、连接失败保留旧结果且不刷新素材', async () => {
  const exports = {}, hooks = {}
  let fail = false, refreshed = 0
  let row = { id:'3', kind:'image', orchestrationState:'submitting', upstreamState:'not_submitted', archiveSummary:{ready:0,failed:0,pending:0} }
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useCreationProgress.ts'), 'utf8')
  runInNewContext(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText, {
    exports, AbortController, Error, setTimeout:()=>1, clearTimeout:()=>{},
    require: name => name === 'vue' ? {...vue,onActivated:()=>{},onDeactivated:()=>{},onBeforeUnmount:fn=>{hooks.close=fn}}
      : name === '@/stores/auth' ? {useAuthStore:()=>({token:'token'})}
      : {listGenerations:async()=>{if(fail)throw new Error('离线'); return {rows:[row]}}},
  })
  const scope=vue.effectScope()
  const state=scope.run(()=>exports.useCreationProgress(()=> '2',()=> '5',()=>undefined,()=>{refreshed++}))
  await Promise.resolve()
  await state.reload()
  assert.equal(state.running.value.id,'3')
  assert.equal(refreshed,0)
  row={...row,orchestrationState:'submission_unknown',upstreamState:'unknown'}
  await state.reload()
  assert.equal(state.running.value,undefined)
  assert.equal(state.uncertain.value.id,'3')
  assert.equal(refreshed,0)
  const checked=state.lastChecked.value
  fail=true
  await state.reload()
  assert.equal(state.error.value,'离线')
  assert.equal(state.lastChecked.value,checked)
  assert.equal(state.rows.value[0].id,'3')
  hooks.close(); scope.stop()
})

test('人工核查停止轮询，连续三次失败停止重试，手动刷新可恢复', async () => {
  const exports = {}, timers = new Map(), hooks = {}
  let seq = 0, fail = false, calls = 0
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useCreationProgress.ts'), 'utf8')
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, Error,
    setTimeout: (fn, ms) => { const id = ++seq; timers.set(id, { fn, ms }); return id },
    clearTimeout: id => timers.delete(id),
    require: name => name === 'vue' ? { ...vue, onActivated: () => {}, onDeactivated: () => {}, onBeforeUnmount: fn => { hooks.close = fn } }
      : name === '@/stores/auth' ? { useAuthStore: () => ({ token: 'token' }) }
      : { listGenerations: async () => { calls++; if (fail) throw new Error('离线'); return { rows: [{ id: '3', orchestrationState: 'submission_unknown', upstreamState: 'unknown', archiveSummary: { ready: 0, pending: 0 } }] } } },
  })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useCreationProgress(() => '2', () => '5', () => undefined, () => {}))
  await state.reload()
  assert.equal(timers.size, 0)
  assert.equal(state.autoUpdating.value, false)
  fail = true
  const before = calls
  await state.reload()
  for (let i = 0; i < 2; i++) {
    const [id, timer] = [...timers.entries()].find(([, t]) => t.ms === 5000)
    timers.delete(id); timer.fn(); await new Promise(resolve => setImmediate(resolve))
  }
  assert.equal(calls - before, 3)
  assert.equal(timers.size, 0)
  assert.equal(state.autoUpdating.value, false)
  assert.equal(state.rows.value[0].id, '3')
  fail = false
  await state.reload()
  assert.equal(state.error.value, '')
  assert.equal(timers.size, 0)
  hooks.close(); scope.stop()
})

test('新任务不在当前目录时按编号追踪，受理后立即进入等待状态', async () => {
  const exports = {}, hooks = {}, accepted = vue.ref(undefined), details = []
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useCreationProgress.ts'), 'utf8')
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, Error, setTimeout: () => 1, clearTimeout: () => {},
    require: name => name === 'vue' ? { ...vue, onActivated: () => {}, onDeactivated: () => {}, onBeforeUnmount: fn => { hooks.close = fn } }
      : name === '@/stores/auth' ? { useAuthStore: () => ({ token: 'token' }) }
      : { listGenerations: async () => ({ rows: [] }), getGeneration: async id => { details.push(id); return { data: { id, projectId:'2', orchestrationState:'submitting', upstreamState:'not_submitted', archiveSummary:{ready:0,pending:0} } } } },
  })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useCreationProgress(() => '2', () => '5', () => accepted.value, () => {}))
  await state.reload()
  accepted.value = '5'
  assert.equal(state.awaitingAccepted.value, true)
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(details, ['5'])
  assert.equal(state.running.value.id, '5')
  assert.equal(state.awaitingAccepted.value, false)
  assert.equal(state.autoUpdating.value, true)
  hooks.close(); scope.stop()
})
