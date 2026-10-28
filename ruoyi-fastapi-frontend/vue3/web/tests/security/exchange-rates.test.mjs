import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'

test('汇率按需查询，筛选切换阻断旧结果，撤权清空来源和汇率', async () => {
  const calls = [],
    hooks = {},
    user = reactive({ permissions: ['billing:price:read'] })
  const context = createContext({ AbortController })
  const mocks = {
    vue: {
      computed,
      reactive,
      ref,
      watch,
      onDeactivated: (fn) => {
        hooks.deactivate = fn
      },
      onBeforeUnmount: () => {},
    },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/prices': {
      listExchangeRates: (params, signal) =>
        new Promise((resolve) => calls.push({ params, signal, resolve })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/useExchangeRates.js', import.meta.url),
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
    state = scope.run(() => module.namespace.useExchangeRates())
  assert.equal(calls.length, 0)
  state.open.value = true
  assert.equal(calls.length, 1)
  state.filters.baseCurrency = 'USD'
  assert.equal(calls[0].signal.aborted, true)
  const latest = state.search()
  calls[0].resolve({ rows: [{ id: 'old' }], total: 1 })
  calls[1].resolve({ rows: [{ id: '1', rate: '0.000000000001', sourceId: '9' }], total: 1 })
  await latest
  assert.equal(calls[1].params.baseCurrency, 'USD')
  assert.equal(state.rows.value[0].rate, '0.000000000001')
  state.select(state.rows.value[0])
  assert.equal(state.selected.value.sourceId, '9')
  user.permissions = []
  assert.equal(state.open.value, false)
  assert.equal(state.rows.value.length, 0)
  assert.equal(state.selected.value, undefined)
  user.permissions = ['billing:price:read']
  state.open.value = true
  hooks.deactivate()
  calls[2].resolve({ rows: [{ id: 'late' }], total: 1 })
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.rows.value.length, 0)
  scope.stop()
})
