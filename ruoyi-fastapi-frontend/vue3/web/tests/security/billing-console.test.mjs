import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'

test('费用列表和明细隔离迟到结果，页面退出清除金额并重新鉴权', async () => {
  const hooks = {}, lists = [], details = [], summaries = []
  const user = reactive({ token: 'session-one', id: '1', permissions: ['billing:read'] })
  const context = createContext({ AbortController })
  const mocks = {
    '@/store/modules/user': { default: () => user },
    '@/utils/billingQuery': { billingTimeWindow: range => range?.length ? { from: '2026-10-01T00:00:00+08:00', to: '2026-10-28T00:00:00+08:00' } : {} },
    vue: { computed, reactive, ref, watch,
      onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn },
      onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn },
    },
    '@/api/studio/billing': {
      getBillingSummary: (params, signal) => new Promise(resolve => summaries.push({ params, signal, resolve })),
      listBillingEvents: (params, signal) => new Promise((resolve, reject) => lists.push({ params, signal, resolve, reject })),
      getBillingEvent: (id, signal) => new Promise(resolve => details.push({ id, signal, resolve })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useBillingEvents.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope()
  const state = scope.run(() => module.namespace.useBillingEvents())
  const flush = () => new Promise(resolve => setImmediate(resolve))
  hooks.mount()
  hooks.activate()
  assert.equal(lists.length, 1)
  state.filters.purpose = 'procurement'
  assert.equal(lists[0].signal.aborted, true)
  lists[0].resolve({ rows: [{ amount: '999' }], total: 1 })
  await flush()
  assert.equal(state.rows.value.length, 0)
  const reading = state.load()
  assert.equal(lists[1].params.purpose, 'procurement')
  lists[1].resolve({ rows: [{ id: '2', amount: '1.0000000001' }], total: 1 })
  await reading
  const first = state.select({ id: '2' }), second = state.select({ id: '3' })
  assert.equal(details[0].signal.aborted, true)
  details[1].resolve({ data: { id: '3' } })
  await second
  details[0].resolve({ data: { id: '2' } })
  await first
  assert.equal(state.detail.value.id, '3')
  hooks.deactivate()
  assert.equal(state.rows.value.length, 0)
  assert.equal(state.detail.value, undefined)
  hooks.activate()
  lists[2].reject(new Error('权限已撤销'))
  await flush()
  assert.equal(state.rows.value.length, 0)
  assert.ok(state.error.value)
  state.filters.mode = 'summary'
  await state.load()
  assert.equal(summaries.length, 0)
  assert.ok(state.error.value)
  state.filters.timeRange = ['start', 'end']
  state.filters.jobId = '999'
  state.filters.state = 'pending'
  state.filters.userId = '9007199254740993'
  state.filters.groupBy = 'department'
  const summaryRead = state.load()
  assert.equal(summaries[0].params.jobId, undefined)
  assert.equal(summaries[0].params.state, undefined)
  assert.equal(summaries[0].params.pageNum, undefined)
  assert.equal(summaries[0].params.userId, '9007199254740993')
  assert.equal(summaries[0].params.groupBy, 'department')
  assert.equal(summaries[0].params.purpose, 'procurement')
  summaries[0].resolve({ data: { rows: [{ totalKnownAmount: '0.0000000001' }] } })
  await summaryRead
  assert.equal(state.summary.value.rows[0].totalKnownAmount, '0.0000000001')
  state.filters.scope = 'cost_center'
  state.filters.costCenterId = '9007199254740993'
  state.filters.projectId = '123'
  const centers = state.load()
  assert.equal(summaries[1].params.scope, 'cost_center')
  assert.equal(summaries[1].params.costCenterId, '9007199254740993')
  assert.equal(summaries[1].params.groupBy, 'cost_center')
  assert.equal(summaries[1].params.projectId, undefined)
  assert.equal(summaries[1].params.userId, undefined)
  assert.equal(summaries[1].params.jobId, undefined)
  state.filters.scope = 'project'
  assert.equal(summaries[1].signal.aborted, true)
  summaries[1].resolve({ data: { rows: [{ totalKnownAmount: '999' }] } })
  await centers
  assert.equal(state.summary.value, undefined)
  assert.equal(state.filters.groupBy, 'department')
  const projects = state.load()
  assert.equal(summaries[2].params.groupBy, 'department')
  assert.equal(summaries[2].params.costCenterId, undefined)
  summaries[2].resolve({ data: { rows: [] } })
  await projects
  state.filters.mode = 'events'
  assert.equal(state.summary.value, undefined)
  const oldList = state.load()
  const previous = lists.at(-1)
  user.token = 'session-two'
  assert.equal(previous.signal.aborted, true)
  previous.resolve({ rows: [{ id: 'old', amount: '999' }], total: 1 })
  await oldList
  assert.equal(state.rows.value.length, 0)
  lists.at(-1).resolve({ rows: [{ id: 'new', amount: '2' }], total: 1 })
  await flush()
  assert.equal(state.rows.value[0].id, 'new')
  const oldDetail = state.select({ id: 'new' })
  const previousDetail = details.at(-1)
  user.id = '2'
  assert.equal(previousDetail.signal.aborted, true)
  previousDetail.resolve({ data: { id: 'old', amount: '999' } })
  await oldDetail
  assert.equal(state.detail.value, undefined)
  user.permissions = []
  const count = lists.length
  await state.load()
  await state.select({ id: 'new' })
  assert.equal(state.allowed.value, false)
  assert.equal(lists.length, count)
  assert.equal(state.rows.value.length, 0)
  assert.equal(state.detailOpen.value, false)
  hooks.unmount()
  scope.stop()
})
