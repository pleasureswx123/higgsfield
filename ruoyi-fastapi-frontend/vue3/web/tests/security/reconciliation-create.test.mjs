import assert from 'node:assert/strict'
import test from 'node:test'
import { File } from 'node:buffer'
import { webcrypto } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, ref, reactive, watch, effectScope } from 'vue'
import { reconciliationInput } from '../../src/utils/reconciliationInput.js'
import { documentUploadItem } from '../../src/utils/documentUpload.js'

const values = () => ({ accountId: '9007199254740993', period: ['2026-01-01 08:00:00', '2026-02-01 08:00:00'] })
test('账号大ID与上海账期精确转换，拒绝空账期和反向区间', () => {
  const data = reconciliationInput(values())
  assert.equal(data.accountId, '9007199254740993')
  assert.equal(Date.parse(data.periodStart), Date.parse('2026-01-01T00:00:00Z'))
  for (const changes of [{ accountId: '0' }, { accountId: '9223372036854775808' }, { period: [] },
    { period: ['2026-02-01 00:00:00', '2026-01-01 00:00:00'] }])
    assert.throws(() => reconciliationInput({ ...values(), ...changes }))
})

test('账单受理失败保留上传用途和幂等键，成功只显示待解析回执', async () => {
  const calls = [], uploads = [], hooks = {}, user = reactive({ permissions: ['billing:read', 'billing:reconcile'] })
  let saved = 0
  const context = createContext({ crypto: webcrypto, AbortController })
  const mocks = {
    vue: { computed, ref, reactive, watch, onDeactivated: fn => { hooks.deactivated = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user }, '@/api/studio/documentUploads': {},
    '@/utils/reconciliationInput': { reconciliationInput },
    '@/utils/documentUpload': { documentUploadItem, uploadDocument: async item => { uploads.push(item); return '9' } },
    '@/api/studio/reconciliations': { createReconciliation: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useReconciliationCreate.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useReconciliationCreate(() => { saved++ }))
  const flush = () => new Promise(resolve => setImmediate(resolve))
  state.formRef.value = { validate: async () => true }
  state.start(); Object.assign(state.form, values())
  await state.submit()
  assert.equal(calls.length, 0)
  state.selectFile(new File(['externalLineKey,currency,amount\na,USD,1'], 'bill.csv'))
  const first = state.submit()
  await flush()
  assert.equal(uploads[0].purpose, 'reconciliation')
  assert.equal(hooks.leave(), false)
  state.close(); assert.equal(state.open.value, true)
  calls[0].reject(Error('响应丢失')); await first
  const retry = state.submit(); await flush()
  assert.equal(calls[1].args[1], calls[0].args[1])
  assert.equal(calls[1].args[0].uploadId, '9')
  assert.equal(uploads[0], uploads[1])
  calls[1].resolve({ data: { id: '8', accepted: true, state: 'pending' } }); await retry
  assert.equal(saved, 1)
  assert.equal(state.receipt.value.state, 'pending')
  await state.submit(); assert.equal(calls.length, 2)
  state.start(); Object.assign(state.form, values())
  state.selectFile(new File(['a,b,c'], 'bill.csv'))
  const late = state.submit(); await flush()
  user.permissions = []
  calls[2].resolve({ data: { id: '10', accepted: true, state: 'pending' } }); await late
  assert.equal(state.receipt.value, undefined)
  assert.equal(saved, 1)
  hooks.unmount(); scope.stop()
})
