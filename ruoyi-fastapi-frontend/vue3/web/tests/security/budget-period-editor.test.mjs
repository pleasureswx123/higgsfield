import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'
import { budgetPeriodPayload } from '../../src/utils/budgetPeriod.js'

test('周期失败保留输入与幂等键，调整不发送预占或消费字段，提交中不能切换对象', async () => {
  const calls = [], hooks = {}, user = reactive({ permissions: ['billing:budget'] })
  let saved = 0
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { computed, reactive, ref, onBeforeUnmount: fn => { hooks.unmount = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/utils/budgetPeriod': { budgetPeriodPayload },
    '@/api/studio/budgets': {
      createBudgetPeriod: (...args) => new Promise((resolve, reject) => calls.push({ kind: 'create', args, resolve, reject })),
      adjustBudgetLimit: (...args) => new Promise(resolve => calls.push({ kind: 'adjust', args, resolve })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useBudgetPeriodEditor.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const state = module.namespace.useBudgetPeriodEditor(() => { saved++ })
  const flush = () => new Promise(resolve => setImmediate(resolve))
  const budget = { id: '9007199254740993', cycleKind: 'monthly', businessTimezone: 'Asia/Shanghai' }
  state.start(budget)
  state.formRef.value = { validate: async () => true }
  Object.assign(state.form, { month: '2026-12', amount: '12.0000000001', reason: '初始额度' })
  const first = state.submit(); await state.submit(); await flush()
  state.start({ ...budget, id: '2' }); state.close()
  assert.equal(state.budget.value.id, budget.id)
  assert.equal(state.open.value, true)
  assert.equal(hooks.leave(), false)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].args[1].limitAmount, '12.0000000001')
  calls[0].reject(new Error('响应丢失')); await first
  assert.equal(state.form.amount, '12.0000000001')
  const retry = state.submit(); await flush()
  assert.equal(calls[0].args[2], calls[1].args[2])
  calls[1].resolve({}); await retry
  assert.equal(saved, 1)
  state.start(budget, { id: '30', revision: '9007199254740994', limitAmount: '12.0000000001' })
  Object.assign(state.form, { amount: '0', reason: '调整额度' })
  const adjustment = state.submit(); await flush()
  assert.equal(calls[2].kind, 'adjust')
  assert.equal(calls[2].args[0], '30')
  assert.deepEqual(calls[2].args[1], { revision: '9007199254740994', newLimit: '0', reason: '调整额度' })
  calls[2].resolve({}); await adjustment
  user.permissions = []
  state.start(budget); await state.submit()
  assert.equal(calls.length, 3)
  hooks.unmount()
})
