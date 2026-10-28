import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { webcrypto } from 'node:crypto'
test('治理保留修订与重试键，状态门禁和撤权清理有效', async () => {
  const calls = [],
    reads = [],
    hooks = {},
    user = reactive({ permissions: ['project:govern'] })
  const context = createContext({ crypto: webcrypto, AbortController })
  const mocks = {
    vue: {
      computed,
      reactive,
      ref,
      watch,
      onMounted: (fn) => {
        hooks.mount = fn
      },
      onActivated: () => {},
      onDeactivated: (fn) => {
        hooks.deactivate = fn
      },
      onBeforeUnmount: () => {},
    },
    'vue-router': {
      onBeforeRouteLeave: (fn) => {
        hooks.leave = fn
      },
    },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/governance': {
      listGovernedProjects: (params, signal) =>
        new Promise((resolve) => reads.push({ params, signal, resolve })),
      governProject: (...args) =>
        new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/useProjectGovernance.js', import.meta.url),
      'utf8'
    ),
    { context }
  )
  await module.link(
    (name) =>
      new SyntheticModule(
        Object.keys(mocks[name]),
        function () {
          for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
        },
        { context }
      )
  )
  await module.evaluate()
  const scope = effectScope(),
    state = scope.run(() => module.namespace.useProjectGovernance())
  hooks.mount()
  state.filters.q = '新项目'
  assert.equal(reads[0].signal.aborted, true)
  reads[0].resolve({ rows: [{ id: 'old' }], total: 1 })
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.rows.value.length, 0)
  const row = { id: '1', revision: '9', status: 'active' }
  state.start(row, 'restore')
  assert.equal(state.target.value, undefined)
  state.start(row, 'pause')
  row.revision = '10'
  state.reason.value = '治理依据'
  state.formRef.value = { validate: async () => true }
  const flush = () => new Promise((resolve) => setImmediate(resolve))
  const first = state.submit()
  await flush()
  assert.equal(calls[0].args[1].revision, '9')
  assert.equal(hooks.leave(), false)
  calls[0].reject(new Error('网络失败'))
  await first
  const retry = state.submit()
  await flush()
  assert.equal(calls[1].args[2], calls[0].args[2])
  user.permissions = []
  calls[1].resolve({})
  await retry
  assert.equal(state.target.value, undefined)
  assert.equal(state.rows.value.length, 0)
  assert.equal(state.pending.value, false)
  hooks.deactivate()
  scope.stop()
})
