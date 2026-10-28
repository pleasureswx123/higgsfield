import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, ref, reactive, watch, effectScope } from 'vue'

test('对账筛选快照、分页、批次切换与撤权隔离迟到结果', async () => {
  const requests = [], batches = [], lines = [], downloads = [], saved = [], hooks = {}
  const user = reactive({ permissions: ['billing:read'] })
  const context = createContext({ AbortController })
  const mocks = {
    vue: { computed, ref, reactive, watch, onMounted: fn => { hooks.mounted = fn },
      onActivated: fn => { hooks.activated = fn }, onDeactivated: fn => { hooks.deactivated = fn },
      onBeforeUnmount: fn => { hooks.unmount = fn } },
    '@/store/modules/user': { default: () => user },
    'file-saver': { saveAs: (...args) => saved.push(args) },
    '@/api/studio/reconciliations': {
      downloadReconciliation: (id, signal) => new Promise(resolve => downloads.push({ id, signal, resolve })),
      listReconciliations: (params, signal) => new Promise((resolve, reject) => requests.push({ params, signal, resolve, reject })),
      getReconciliation: (id, signal) => new Promise((resolve, reject) => batches.push({ id, signal, resolve, reject })),
      listReconciliationLines: (id, params, signal) => new Promise((resolve, reject) => lines.push({ id, params, signal, resolve, reject })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useReconciliations.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useReconciliations())
  const flush = () => new Promise(resolve => setImmediate(resolve))
  state.formRef.value = { validate: async () => true }
  state.filters.accountId = '123'
  const search = state.search()
  await flush()
  assert.equal(requests[0].params.accountId, '123')
  requests[0].resolve({ rows: [{ id: '1' }, { id: '2' }], total: 21 })
  await search
  state.filters.accountId = '999'
  state.page.value = 2
  const paging = state.load()
  assert.equal(requests[1].params.accountId, '123')
  assert.equal(requests[1].params.pageNum, 2)
  requests[1].resolve({ rows: [{ id: '1' }, { id: '2' }], total: 21 })
  await paging
  await state.select({ id: 'not-listed' })
  assert.equal(batches.length, 0)
  const old = state.select({ id: '1' }), current = state.select({ id: '2' })
  assert.equal(batches[0].signal.aborted, true)
  batches[0].resolve({ data: { id: '1' } }); lines[0].resolve({ rows: [{ amount: 'old' }], total: 1 })
  await old
  assert.equal(state.detail.value, undefined)
  batches[1].resolve({ data: { id: '2', attachment: { fileName: '账单.csv', byteSize: '3' } } })
  lines[1].resolve({ rows: [{ observationId: '9', amount: '0.0000000001' }], total: 1 })
  await current
  assert.equal(state.detail.value.id, '2')
  assert.equal(state.lines.value[0].amount, '0.0000000001')
  const bad = state.download()
  downloads[0].resolve({ type: 'application/json', size: 3 }); await bad
  assert.equal(saved.length, 0)
  assert.ok(state.downloadError.value)
  const good = state.download()
  downloads[1].resolve({ type: 'text/csv', size: 3 }); await good
  assert.equal(saved[0][1], '账单.csv')
  const late = state.download()
  const revoked = state.loadDetail()
  user.permissions = []
  assert.equal(downloads[2].signal.aborted, true)
  downloads[2].resolve({ type: 'text/csv', size: 3 }); await late
  assert.equal(saved.length, 1)
  assert.equal(batches[2].signal.aborted, true)
  batches[2].resolve({ data: { id: '2' } }); lines[2].resolve({ rows: [{ id: 'secret' }], total: 1 })
  await revoked
  assert.equal(state.detail.value, undefined)
  assert.equal(state.rows.value.length, 0)
  assert.equal(state.lines.value.length, 0)
  user.permissions = ['billing:read']
  assert.equal(requests.length, 3)
  hooks.deactivated()
  requests[2].resolve({ rows: [{ id: 'late' }], total: 1 })
  await flush()
  assert.equal(state.rows.value.length, 0)
  hooks.unmount()
  scope.stop()
})
