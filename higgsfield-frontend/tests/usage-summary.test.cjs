const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
function load(file, requireMock = require) {
  const exports = {}
  const source = readFileSync(join(__dirname, '../src', file), 'utf8')
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    { exports, require: requireMock, AbortController })
  return exports
}
const dates = load('utils/usage.ts')
const flush = async () => { await vue.nextTick(); await new Promise(resolve => setImmediate(resolve)) }

test('上海自然日含结束日且不依赖浏览器时区，拒绝非法或超长日期', () => {
  const window = dates.usageWindow(['2026-10-01', '2026-10-28'])
  assert.equal(window.from, '2026-09-30T16:00:00.000Z')
  assert.equal(window.to, '2026-10-28T16:00:00.000Z')
  assert.equal(dates.defaultUsageDates(new Date('2026-09-30T17:00:00Z')).join(','), '2026-10-01,2026-10-01')
  for (const value of [[], ['2026-02-30', '2026-03-01'], ['2026-10-28', '2026-10-27'], ['2025-01-01', '2026-01-02']])
    assert.throws(() => dates.usageWindow(value))
  assert.equal(dates.usageWindow(['2024-02-29', '2024-02-29']).to, '2024-02-29T16:00:00.000Z')
})

test('筛选改变或缓存页面离开后不接受旧数据，重新进入重新请求权限', async () => {
  const hooks = {}, requests = []
  const api = load('composables/useUsageSummary.ts', name => {
    if (name === 'vue') return { ...vue,
      onMounted: fn => { hooks.mount = fn },
      onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn },
      onBeforeUnmount: fn => { hooks.unmount = fn },
    }
    if (name === '@/utils/usage') return dates
    return { getPersonalUsageSummary: (params, signal) => new Promise((resolve, reject) => requests.push({ params, signal, resolve, reject })) }
  })
  const scope = vue.effectScope()
  const state = scope.run(() => api.useUsageSummary())
  hooks.activate()
  state.filters.groupBy = 'day'
  assert.equal(requests[0].signal.aborted, true)
  requests[0].resolve({ data: { rows: [{ totalKnownAmount: '999' }] } })
  await flush()
  assert.equal(state.summary.value, undefined)
  hooks.deactivate()
  hooks.activate()
  assert.equal(requests[1].params.groupBy, 'day')
  requests[1].resolve({ data: { rows: [{ totalKnownAmount: '2' }] } })
  await flush()
  assert.equal(state.summary.value.rows[0].totalKnownAmount, '2')
  hooks.deactivate()
  assert.equal(state.summary.value, undefined)
  hooks.activate()
  requests[2].reject(new Error('没有费用读取权限'))
  await flush()
  assert.equal(state.summary.value, undefined)
  assert.ok(state.error.value)
  hooks.unmount()
  scope.stop()
})

test('项目页隐藏用量时不读取，切换项目取消旧请求，挂载激活不重复读取', async () => {
  const hooks = {}, requests = [], project = vue.ref('1'), active = vue.ref(false)
  const api = load('composables/useUsageSummary.ts', name => {
    if (name === 'vue') return { ...vue,
      onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn },
      onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn },
    }
    if (name === '@/utils/usage') return dates
    return {
      getPersonalUsageSummary: () => { throw new Error('不得回退到本人范围') },
      getProjectUsageSummary: (id, params, signal) => new Promise(resolve => requests.push({ id, params, signal, resolve })),
    }
  })
  const scope = vue.effectScope()
  const state = scope.run(() => api.useUsageSummary(() => project.value, () => active.value))
  hooks.mount()
  hooks.activate()
  assert.equal(requests.length, 0)
  active.value = true
  hooks.activate()
  assert.equal(requests.length, 1)
  assert.equal(requests[0].id, '1')
  project.value = '2'
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(requests[1].id, '2')
  requests[0].resolve({ data: { rows: [{ totalKnownAmount: '999' }] } })
  await flush()
  assert.equal(state.summary.value, undefined)
  active.value = false
  assert.equal(requests[1].signal.aborted, true)
  requests[1].resolve({ data: { rows: [{ totalKnownAmount: '888' }] } })
  await flush()
  assert.equal(state.summary.value, undefined)
  hooks.unmount()
  scope.stop()
})
