import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
const context = createContext({ AbortController })
const routing = new SourceTextModule(
  await readFile(new URL('../../src/utils/routing.js', import.meta.url), 'utf8'),
  { context }
)
await routing.link(() => {})
await routing.evaluate()
const utils = new SourceTextModule(
  await readFile(new URL('../../src/utils/priceSimulation.js', import.meta.url), 'utf8'),
  { context }
)
await utils.link(() => routing)
await utils.evaluate()
const { priceSimulationPayload, simulationFields } = utils.namespace
const form = () => ({
  dimensions: '{}',
  exchangeRateVersionId: '',
  ...Object.fromEntries(simulationFields.map(([name]) => [name, ''])),
})

test('未知用量省略，已知零保留，大整数及秒数不丢精度', () => {
  const input = form()
  input.inputTokens = '9223372036854775807'
  input.imageCount = '0'
  input.outputSeconds = '999999999999999999.123456'
  const result = priceSimulationPayload(input)
  assert.equal(result.usage.inputTokens, input.inputTokens)
  assert.equal(result.usage.imageCount, 0)
  assert.equal(result.usage.outputTokens, undefined)
  assert.equal(result.usage.outputSeconds, input.outputSeconds)
  for (const change of [
    { imageCount: '2147483648' },
    { inputTokens: '9223372036854775808' },
    { outputSeconds: '-1' },
    { dimensions: '{"x":9007199254740993}' },
    { dimensions: '{"x":null}' },
    { dimensions: '[]' },
  ])
    assert.throws(() => priceSimulationPayload({ ...form(), ...change }))
})

test('试算输入改变与撤权丢弃迟到金额，保留输入可重新计算', async () => {
  const calls = [],
    hooks = {},
    user = reactive({ permissions: ['billing:price:read'] }),
    id = ref('1')
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
      simulatePrice: (id, data, signal) =>
        new Promise((resolve) => calls.push({ id, data, signal, resolve })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/usePriceSimulation.js', import.meta.url),
      'utf8'
    ),
    { context }
  )
  await module.link((name) =>
    name === '@/utils/priceSimulation'
      ? utils
      : new SyntheticModule(
          Object.keys(mocks[name]),
          function () {
            for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
          },
          { context }
        )
  )
  await module.evaluate()
  const scope = effectScope(),
    state = scope.run(() => module.namespace.usePriceSimulation(() => id.value))
  state.formRef.value = { validate: async () => true }
  const flush = () => new Promise((resolve) => setImmediate(resolve))
  const first = state.submit()
  await flush()
  state.form.imageCount = '2'
  assert.equal(calls[0].signal.aborted, true)
  calls[0].resolve({ data: { total: '1.0000000000' } })
  await first
  assert.equal(state.result.value, undefined)
  const second = state.submit()
  await flush()
  calls[1].resolve({ data: { total: '2.0000000001' } })
  await second
  assert.equal(state.result.value.total, '2.0000000001')
  const third = state.submit()
  await flush()
  user.permissions = []
  calls[2].resolve({ data: { total: '3' } })
  await third
  assert.equal(state.result.value, undefined)
  assert.equal(state.form.imageCount, '2')
  hooks.deactivate()
  scope.stop()
})
