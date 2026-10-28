const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const flush = async () => { await vue.nextTick(); await new Promise(resolve => setImmediate(resolve)) }

test('切换项目隔离迟到预算，刷新清除旧额度，卸载取消请求', async () => {
  const exports = {}, requests = [], hooks = {}, project = vue.ref('1'), refreshKey = vue.ref()
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useBudgetStatus.ts'), 'utf8')
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController,
    require: name => name === 'vue' ? { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn } } : {
      getBudgetStatus: (id, signal) => new Promise(resolve => requests.push({ id, signal, resolve })),
    },
  })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useBudgetStatus(() => project.value, () => refreshKey.value))
  project.value = '2'
  await flush()
  assert.equal(requests[0].signal.aborted, true)
  requests[1].resolve({ data: { canSubmit: true, amountVisibility: 'hidden' } })
  await flush()
  requests[0].resolve({ data: { canSubmit: false, periods: [{ availableAmount: '999' }] } })
  await flush()
  assert.equal(state.status.value.amountVisibility, 'hidden')
  assert.equal(state.status.value.periods, undefined)
  refreshKey.value = 'accepted-task'
  await flush()
  assert.equal(state.status.value, undefined)
  assert.equal(requests.length, 3)
  hooks.unmount()
  scope.stop()
  assert.equal(requests[2].signal.aborted, true)
  requests[2].resolve({ data: { periods: [{ availableAmount: '100' }] } })
  await flush()
  assert.equal(state.status.value, undefined)
})
