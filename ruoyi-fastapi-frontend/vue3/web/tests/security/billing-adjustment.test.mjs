import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch } from 'vue'
import { webcrypto } from 'node:crypto'

test('调整保留精度、版本及失败重试键，防止连点并检查权限', async () => {
  const calls = [], hooks = {}, user = reactive({ token: 'one', id: '1', permissions: ['billing:adjust'] })
  let saved = 0
  const context = createContext({ crypto: webcrypto, AbortController })
  const mocks = {
    vue: { computed, reactive, ref, watch, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } },
    '@/store/modules/user': { default: () => user },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/api/studio/billing': { adjustBillingEvent: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useBillingAdjustment.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const event = { id: '9007199254740993', revision: '9007199254740994', amount: '12.0000000001' }
  const state = module.namespace.useBillingAdjustment(() => event, () => { saved++ })
  state.formRef.value = { validate: async () => true }
  state.form.deltaAmount = '-0.0000000001'
  state.form.reason = '  核实退款  '
  state.form.reconciliationLineId = ' 9007199254740995 '
  const flush = () => new Promise(resolve => setImmediate(resolve))
  const first = state.submit()
  await state.submit()
  await flush()
  assert.equal(calls.length, 1)
  assert.equal(hooks.leave(), false)
  assert.equal(calls[0].args[0], event.id)
  assert.equal(calls[0].args[1].revision, event.revision)
  assert.equal(calls[0].args[1].deltaAmount, '-0.0000000001')
  assert.equal(calls[0].args[1].reason, '核实退款')
  assert.equal(calls[0].args[1].reconciliationLineId, '9007199254740995')
  calls[0].reject(new Error('响应丢失'))
  await first
  assert.equal(hooks.leave(), false)
  assert.equal(state.uncertain.value, true)
  assert.equal(state.form.deltaAmount, '-0.0000000001')
  assert.ok(state.error.value)
  state.form.deltaAmount = '999'
  state.form.reason = '不能改原调整'
  const retry = state.submit()
  await flush()
  assert.equal(calls[0].args[2], calls[1].args[2])
  assert.equal(calls[1].args[1].deltaAmount, '-0.0000000001')
  assert.equal(calls[1].args[1].reason, '核实退款')
  calls[1].resolve({})
  await retry
  assert.equal(saved, 1)
  user.permissions = []
  await state.submit()
  assert.equal(calls.length, 2)
  user.permissions = ['billing:adjust']
  event.amount = null
  await state.submit()
  assert.equal(calls.length, 2)
  event.amount = '1'
  state.form.deltaAmount = '1'
  state.form.reason = '核对'
  const stale = state.submit()
  await flush()
  user.id = '2'
  assert.equal(calls[2].args[3].aborted, true)
  assert.equal(state.uncertain.value, false)
  state.form.reason = '新用户输入'
  calls[2].resolve({})
  await stale
  assert.equal(saved, 1)
  assert.equal(state.form.reason, '新用户输入')
  state.form.deltaAmount = '2'
  const rejection = state.submit()
  await flush()
  calls[3].reject(Object.assign(new Error('版本已变化'), { code: 601, errorCode: 'REVISION_CONFLICT' }))
  await rejection
  assert.equal(state.uncertain.value, false)
  assert.equal(hooks.leave(), true)
  hooks.unmount()
  await state.submit()
  assert.equal(calls.length, 4)
})
