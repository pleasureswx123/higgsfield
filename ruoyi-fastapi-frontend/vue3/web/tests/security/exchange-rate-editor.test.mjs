import assert from 'node:assert/strict'
import test from 'node:test'
import { exchangeRatePayload, exchangeRatePublishPayload } from '../../src/utils/exchangeRate.js'
const form = () => ({
  baseCurrency: 'USD',
  quoteCurrency: 'CNY',
  rate: '0.000000000001',
  sourceId: '9007199254740993',
  validFrom: '2026-11-01 00:00:00',
  validUntil: '',
})
test('汇率保持12位精度和大整数来源，禁止零值同币对与逆序区间', () => {
  const result = exchangeRatePayload(form())
  assert.equal(result.rate, '0.000000000001')
  assert.equal(result.sourceId, '9007199254740993')
  assert.equal(Date.parse(result.validFrom), Date.parse('2026-10-31T16:00:00Z'))
  for (const change of [
    { rate: '0' },
    { rate: '1e-12' },
    { rate: '0.0000000000001' },
    { quoteCurrency: 'USD' },
    { validUntil: '2026-10-01 00:00:00' },
  ])
    assert.throws(() => exchangeRatePayload({ ...form(), ...change }))
  assert.deepEqual(exchangeRatePublishPayload('2', ' 发布依据 '), {
    revision: '2',
    reason: '发布依据',
  })
  assert.throws(() => exchangeRatePublishPayload('2', ' '))
})

import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'
test('汇率发布保留修订快照与失败请求键，登记权限单独校验', async () => {
  const calls = [], user = reactive({ permissions: ['billing:price:publish'] }), hooks = {}
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { computed, reactive, ref, onBeforeUnmount: () => {} },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/utils/exchangeRate': { exchangeRatePayload, exchangeRatePublishPayload },
    '@/api/studio/prices': {
      publishExchangeRate: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
      createExchangeRate: (...args) => new Promise(resolve => calls.push({ args, resolve })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useExchangeRateEditor.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () { for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value) }, { context })); await module.evaluate()
  const state = module.namespace.useExchangeRateEditor(() => {})
  state.start(); assert.equal(state.open.value, false)
  state.start({ id: '1', status: 'published', revision: '2' }); assert.equal(state.open.value, false)
  const row = { id: '1', status: 'draft', revision: '2' }; state.start(row); row.revision = '3'
  state.form.reason = '审核依据'; state.formRef.value = { validate: async () => true }
  const flush = () => new Promise(resolve => setImmediate(resolve))
  const first = state.submit(); await flush(); assert.equal(calls[0].args[1].revision, '2'); assert.equal(hooks.leave(), false)
  calls[0].reject(new Error('网络失败')); await first
  const retry = state.submit(); await flush(); assert.equal(calls[1].args[2], calls[0].args[2]); calls[1].resolve({}); await retry
  user.permissions = ['billing:price:write']; state.start(); Object.assign(state.form, form())
  const create = state.submit(); await flush(); assert.equal(calls[2].args[0].rate, '0.000000000001'); calls[2].resolve({}); await create
})
