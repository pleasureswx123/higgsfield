import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { reactive, ref, computed, watch, effectScope } from 'vue'

test('切换预算取消旧周期和账本，撤销账本权限或离开页面清除旧金额', async () => {
  const hooks = {}, periods = [], ledger = [], user = reactive({ permissions: ['billing:read'] })
  const context = createContext({ AbortController })
  const mocks = {
    vue: { reactive, ref, computed, watch, onMounted: fn => { hooks.mount = fn }, onActivated: () => {},
      onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/budgets': {
      listBudgets: async () => ({ rows: [{ id: '1' }], total: 1 }),
      listBudgetPeriods: (id, params, signal) => new Promise(resolve => periods.push({ id, signal, resolve })),
      listBudgetLedger: (id, params, signal) => new Promise(resolve => ledger.push({ id, signal, resolve })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useBudgets.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useBudgets())
  hooks.mount()
  const first = state.selectBudget({ id: '1' }), second = state.selectBudget({ id: '2' })
  assert.equal(periods[0].signal.aborted, true)
  periods[1].resolve({ rows: [{ id: '20', availableAmount: '-0.0000000001' }], total: 1 })
  await second
  periods[0].resolve({ rows: [{ id: '10' }], total: 1 })
  await first
  assert.equal(state.periods.rows[0].id, '20')
  const detail = state.selectPeriod(state.periods.rows[0])
  user.permissions = []
  assert.equal(ledger[0].signal.aborted, true)
  ledger[0].resolve({ rows: [{ consumedDelta: '999' }], total: 1 })
  await detail
  assert.equal(state.ledger.rows.length, 0)
  assert.equal(state.period.value, undefined)
  hooks.deactivate()
  assert.equal(state.budgets.rows.length, 0)
  assert.equal(state.periods.rows.length, 0)
  hooks.unmount()
  scope.stop()
})
