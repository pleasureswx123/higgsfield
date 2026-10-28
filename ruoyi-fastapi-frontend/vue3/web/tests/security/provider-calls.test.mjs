import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { toRfc3339 } from '../../src/utils/time.js'
import { validRoutingId } from '../../src/utils/routing.js'

test('调用详情切换、筛选和撤权中止旧请求，大整数不转数字', async () => {
  const reads = [], details = [], hooks = {}, user = reactive({ permissions: ['operations:read'] })
  const context = createContext({ AbortController })
  const mocks = {
    vue: { computed, reactive, ref, watch, onMounted: fn => { hooks.mount = fn }, onActivated: () => {},
      onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: () => {} },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/providerCalls': {
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
  scope.stop()
})
