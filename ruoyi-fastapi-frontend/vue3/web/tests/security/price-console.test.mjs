import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'

test('价格跨簿切换阻断旧详情与历史，撤权及离开清空金额', async () => {
  const hooks = {},
    versions = [],
    details = [],
    histories = [],
    user = reactive({ permissions: ['billing:price:read'] })
  const context = createContext({ AbortController })
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
    '@/store/modules/user': { default: () => user },
    '@/utils/routing': { validRoutingId: (value) => /^[1-9]\d*$/.test(value) },
    '@/api/studio/prices': {
      listPriceBooks: async () => ({ rows: [{ id: '1', currency: 'CNY' }], total: 1 }),
      listPriceVersions: (params, signal) =>
        new Promise((resolve) => versions.push({ params, signal, resolve })),
      getPriceVersion: (id, signal) =>
        new Promise((resolve) => details.push({ id, signal, resolve })),
      listPriceHistory: (id, params, signal) =>
        new Promise((resolve) => histories.push({ id, signal, resolve })),
    },
  }
  const module = new SourceTextModule(
    await readFile(new URL('../../src/composables/studio/usePrices.js', import.meta.url), 'utf8'),
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
    state = scope.run(() => module.namespace.usePrices())
  hooks.mount()
  await new Promise((resolve) => setImmediate(resolve))
  const one = state.selectBook({ id: '1' }),
    two = state.selectBook({ id: '2' })
  assert.equal(versions[0].signal.aborted, true)
  versions[0].resolve({ rows: [{ id: '10' }], total: 1 })
  await one
  versions[1].resolve({ rows: [{ id: '20' }], total: 1 })
  await two
  assert.equal(state.versions.rows[0].id, '20')
  const firstDetail = state.selectVersion({ id: '20' }),
    secondDetail = state.selectVersion({ id: '21' })
  details[0].resolve({ data: { id: '20' } })
  await firstDetail
  assert.equal(state.version.value, undefined)
  details[1].resolve({ data: { id: '21', items: [{ unitPrice: '0.0000000001' }] } })
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.version.value.items[0].unitPrice, '0.0000000001')
  user.permissions = []
  assert.equal(histories[0].signal.aborted, true)
  histories[0].resolve({ rows: [{ id: '100' }], total: 1 })
  await secondDetail
  assert.equal(state.version.value, undefined)
  assert.equal(state.history.rows.length, 0)
  assert.equal(state.books.rows.length, 0)
  user.permissions = ['billing:price:read']
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.books.rows.length, 1)
  hooks.deactivate()
  assert.equal(state.books.rows.length, 0)
  scope.stop()
})
