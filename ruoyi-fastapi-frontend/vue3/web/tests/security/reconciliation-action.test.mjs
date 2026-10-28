import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { webcrypto } from 'node:crypto'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'

async function setup() {
  const calls = [], hooks = {}, user = reactive({ permissions: ['billing:read', 'billing:reconcile'] })
  let saved = 0
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { computed, reactive, ref, watch, onDeactivated: fn => { hooks.deactivated = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/reconciliations': { changeReconciliationLine: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useReconciliationAction.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useReconciliationAction(async () => { saved++ }))
  state.formRef.value = { validate: async () => true }
  return { calls, hooks, user, state, scope, saved: () => saved }
}
const row = () => ({ id: '9007199254740993', revision: '2', status: 'unmatched',
  externalLineKey: '0001', amount: '0.0000000001', currency: 'USD', subjectId: null })
const flush = () => new Promise(resolve => setImmediate(resolve))

test('差异处理冻结选中观察证据，保留大ID，失败重试不改变采用依据', async () => {
  const { state, calls, hooks, scope } = await setup()
  assert.equal(state.canStart(row(), 'resolve'), false)
  const source = { ...row(), status: 'disputed', observationId: '9007199254740996',
    sourceEvidence: { amount: '9.0000000001', currency: 'CNY' } }
  state.start(source, 'resolve')
  source.observationId = '99'
  source.sourceEvidence.amount = '999'
  assert.equal(state.target.value.sourceAmount, '9.0000000001')
  state.form.subjectId = '9007199254740995'
  state.form.reason = '采用供应商修订文件'
  const pending = state.submit()
  await flush()
  assert.equal(calls[0].args[1], 'resolve')
  assert.equal(calls[0].args[2].observationId, '9007199254740996')
  assert.equal(calls[0].args[2].subjectId, '9007199254740995')
  calls[0].reject(Error('响应丢失')); await pending
  const retry = state.submit(); await flush()
  assert.equal(calls[1].args[3], calls[0].args[3])
  calls[1].resolve({}); await retry
  state.start({ ...row(), status: 'matched', subjectId: '123', acceptedAmount: '9.0000000001', acceptedCurrency: 'CNY' }, 'confirm')
  assert.equal(state.target.value.amount, '9.0000000001')
  assert.equal(state.target.value.currency, 'CNY')
  hooks.unmount(); scope.stop()
})

test('匹配保留版本和大ID，失败重试同键，成功刷新，提交时不能离开', async () => {
  const { state, calls, hooks, scope, saved } = await setup()
  const source = row()
  state.start(source, 'match')
  source.revision = '3'
  state.form.subjectId = '9007199254740995'
  state.form.reason = '  已核对原始账单  '
  const first = state.submit()
  await flush()
  assert.equal(hooks.leave(), false)
  state.close()
  assert.ok(state.target.value)
  assert.equal(calls[0].args[2].revision, '2')
  assert.equal(calls[0].args[2].subjectId, '9007199254740995')
  assert.equal(calls[0].args[2].reason, '已核对原始账单')
  calls[0].reject(Error('响应丢失'))
  await first
  const retry = state.submit()
  await flush()
  assert.equal(calls[1].args[3], calls[0].args[3])
  calls[1].resolve({})
  await retry
  assert.equal(saved(), 1)
  assert.equal(state.target.value, undefined)
  assert.equal(hooks.leave(), true)
  hooks.unmount(); scope.stop()
})

test('确认只允许已匹配行，撤权阻断迟到成功，输入边界不提交', async () => {
  const { state, calls, user, hooks, scope, saved } = await setup()
  assert.equal(state.canStart(row(), 'confirm'), false)
  assert.equal(state.canStart({ ...row(), status: 'disputed' }, 'match'), false)
  assert.equal(state.canStart({ ...row(), status: 'confirmed' }, 'match'), false)
  state.start(row(), 'match')
  state.form.subjectId = '9223372036854775808'
  state.form.reason = '有效依据'
  await state.submit()
  assert.equal(calls.length, 0)
  assert.match(state.error.value, /计费对象ID/)
  state.start({ ...row(), status: 'matched', subjectId: '123' }, 'confirm')
  state.form.reason = '已经核对'
  const pending = state.submit()
  await flush()
  assert.equal(calls[0].args[1], 'confirm')
  assert.equal(calls[0].args[2].subjectId, undefined)
  user.permissions = ['billing:read']
  calls[0].resolve({})
  await pending
  assert.equal(saved(), 0)
  assert.equal(state.target.value, undefined)
  hooks.unmount(); scope.stop()
})
