import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { toRfc3339 } from '../../src/utils/time.js'
import { validRoutingId } from '../../src/utils/routing.js'

test('调用详情切换、筛选和撤权中止旧请求，大整数不转数字', async () => {
  const reads = [], details = [], processes = [], hooks = {}, user = reactive({ permissions: ['operations:read'] })
  const context = createContext({ AbortController })
  const mocks = {
    vue: { computed, reactive, ref, watch, onMounted: fn => { hooks.mount = fn }, onActivated: () => {},
      onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: () => {} },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/providerCalls': {
      listCallTasks: (params, signal) => new Promise(resolve => reads.push({ params, signal, resolve })),
      getTaskCalls: (id, signal) => new Promise(resolve => processes.push({ id, signal, resolve })),
      listProviderCalls: (params, signal) => new Promise(resolve => reads.push({ params, signal, resolve })),
      getProviderCall: (id, signal) => new Promise(resolve => details.push({ id, signal, resolve })),
    },
    '@/utils/time': { toRfc3339 }, '@/utils/routing': { validRoutingId },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useProviderCalls.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useProviderCalls())
  const flush = () => new Promise(resolve => setImmediate(resolve))
  assert.equal(state.view.value, 'tasks')
  state.view.value = 'calls'
  await flush()
  hooks.mount()
  state.filters.jobId = '9007199254740993'
  const list = state.search()
  assert.equal(reads[0].signal.aborted, true)
  assert.equal(reads[1].params.jobId, '9007199254740993')
  reads[1].resolve({ rows: [{ id: '1' }, { id: '2' }], total: 2 })
  await list
  reads[0].resolve({ rows: [{ id: 'old' }], total: 1 })
  await flush()
  assert.equal(state.rows.value.length, 2)
  const first = state.inspect('1'), second = state.inspect('2')
  assert.equal(details[0].signal.aborted, true)
  details[1].resolve({ data: { id: '2', requestMetadata: {} } })
  await second
  details[0].resolve({ data: { id: '1' } })
  await first
  assert.equal(state.detail.value.id, '2')
  const pending = state.inspect('1')
  user.permissions = []
  assert.equal(details[2].signal.aborted, true)
  details[2].resolve({ data: { id: '1' } })
  await pending
  assert.equal(state.detail.value, undefined)
  assert.equal(state.selectedId.value, '')
  assert.equal(state.rows.value.length, 0)
  user.permissions = ['operations:read']
  hooks.deactivate()
  reads[2].resolve({ rows: [{ id: 'late' }], total: 1 })
  await flush()
  assert.equal(state.rows.value.length, 0)
  hooks.mount()
  Object.assign(state.filters, { jobId: '22', accountId: '3', state: 'completed', from: '2026-11-09 08:00:00', to: '2026-11-09 16:00:00' })
  const ranged = state.search()
  const rangedRead = reads.at(-1)
  assert.equal(rangedRead.params.from, '2026-11-09T08:00:00.000+08:00')
  assert.equal(rangedRead.params.to, '2026-11-09T16:00:00.000+08:00')
  state.page.value = 3
  const reset = state.reset()
  assert.equal(rangedRead.signal.aborted, true)
  assert.equal(JSON.stringify(reads.at(-1).params), JSON.stringify({ pageNum: 1, pageSize: 20 }))
  assert.equal(Object.values(state.filters).every(value => value === ''), true)
  reads.at(-1).resolve({ rows: [{ id: 'reset' }], total: 1 })
  await reset
  rangedRead.resolve({ rows: [{ id: 'stale' }], total: 1 })
  await ranged
  assert.equal(state.rows.value[0].id, 'reset')
  const processFirst = state.inspectProcess('9007199254740993')
  const processSecond = state.inspectProcess('22')
  assert.equal(processes[0].id, '9007199254740993')
  assert.equal(processes[0].signal.aborted, true)
  processes[1].resolve({ data: [{ id: '83' }] })
  await processSecond
  processes[0].resolve({ data: [{ id: 'old' }] })
  await processFirst
  assert.equal(state.processRows.value[0].id, '83')
  const processDetail = state.inspect('83')
  state.closeProcess()
  assert.equal(details.at(-1).signal.aborted, true)
  details.at(-1).resolve({ data: { id: '83' } })
  await processDetail
  assert.equal(state.detail.value, undefined)
  assert.equal(state.processId.value, '')
  scope.stop()
})
