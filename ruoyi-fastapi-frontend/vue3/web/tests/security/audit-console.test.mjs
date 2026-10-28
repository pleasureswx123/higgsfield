import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { toRfc3339 } from '../../src/utils/time.js'
import { validRoutingId } from '../../src/utils/routing.js'

test('审计筛选保持大整数与时区，旧响应、离页与撤权清理差异证据', async () => {
  const reads = [], hooks = {}, user = reactive({ permissions: ['audit:read'] })
  const context = createContext({ AbortController })
  const mocks = {
    vue: { computed, reactive, ref, watch, onMounted: fn => { hooks.mount = fn },
      onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: () => {} },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/audit': { listAuditLogs: (params, signal) => new Promise(resolve => reads.push({ params, signal, resolve })) },
    '@/utils/time': { toRfc3339 }, '@/utils/routing': { validRoutingId },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useAuditLogs.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useAuditLogs())
  const flush = () => new Promise(resolve => setImmediate(resolve))
  hooks.mount()
  state.filters.actorId = '9007199254740993'
  state.filters.from = '2026-10-01 08:00:00'
  assert.equal(reads[0].signal.aborted, true)
  const pending = state.search()
  assert.equal(reads[1].params.actorId, '9007199254740993')
  assert.equal(Date.parse(reads[1].params.from), Date.parse('2026-10-01T00:00:00Z'))
  reads[0].resolve({ rows: [{ id: 'stale' }], total: 1 })
  await flush()
  assert.equal(state.rows.value.length, 0)
  reads[1].resolve({ rows: [{ id: '1', diff: { before: '原值' } }], total: 1 })
  await pending
  state.inspect(state.rows.value[0])
  assert.equal(state.selected.value.id, '1')
  state.filters.objectType = 'project'
  assert.equal(state.selected.value, undefined)
  assert.equal(state.rows.value.length, 0)
  state.filters.actorId = '0'
  await state.search()
  assert.equal(reads.length, 2)
  assert.match(state.error.value, /操作者ID/)
  state.filters.actorId = ''
  const revoked = state.search()
  user.permissions = []
  assert.equal(reads[2].signal.aborted, true)
  reads[2].resolve({ rows: [{ id: 'hidden' }], total: 1 })
  await revoked
  assert.equal(state.rows.value.length, 0)
  user.permissions = ['audit:read']
  assert.equal(reads.length, 4)
  hooks.deactivate()
  reads[3].resolve({ rows: [{ id: 'late' }], total: 1 })
  await flush()
  assert.equal(state.rows.value.length, 0)
  hooks.activate()
  assert.equal(reads.length, 5)
  reads[4].resolve({ rows: [], total: 0 })
  await flush()
  scope.stop()
})
