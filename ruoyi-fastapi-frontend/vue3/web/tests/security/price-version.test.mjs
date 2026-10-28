import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'
const context = createContext({ crypto: webcrypto })
const routing = new SourceTextModule(
  await readFile(new URL('../../src/utils/routing.js', import.meta.url), 'utf8'),
  { context }
)
await routing.link(() => {})
await routing.evaluate()
const utils = new SourceTextModule(
  await readFile(new URL('../../src/utils/priceVersion.js', import.meta.url), 'utf8'),
  { context }
)
await utils.link(() => routing)
await utils.evaluate()
const { priceVersionPayload, emptyPriceItem } = utils.namespace
const form = () => ({
  calculationScale: 10,
  sourceIds: '9007199254740993',
  items: [{ ...emptyPriceItem(), itemCode: 'image_count', unitPrice: '0.0000000001' }],
})

test('计价分项精度、等值阶梯去重、零价依据与白名单', () => {
  const input = form()
  input.items[0].id = '123'
  const payload = priceVersionPayload(input)
  assert.equal(payload.items[0].unitPrice, '0.0000000001')
  assert.equal(payload.items[0].id, undefined)
  assert.equal(payload.sourceIds[0], '9007199254740993')
  input.items[0].quantityFrom = '999999999999999999.999998'
  input.items[0].quantityTo = '999999999999999999.999999'
  assert.equal(priceVersionPayload(input).items[0].quantityTo, '999999999999999999.999999')
  input.items[0].quantityTo = input.items[0].quantityFrom
  assert.throws(() => priceVersionPayload(input), /上限/)
  const duplicate = form()
  duplicate.items.push({ ...duplicate.items[0], quantityFrom: '0.000000' })
  assert.throws(() => priceVersionPayload(duplicate), /重复/)
  const zero = form()
  zero.items[0].unitPrice = '0.0000000000'
  assert.throws(() => priceVersionPayload(zero), /免费依据/)
  zero.items[0].freeReason = '合同免费'
  assert.equal(priceVersionPayload(zero).items[0].freeReason, '合同免费')
  for (const bad of ['1e-10', 0.1, '-1', '0.00000000001']) {
    const input = form()
    input.items[0].unitPrice = bad
    assert.throws(() => priceVersionPayload(input), /精度/)
  }
})

test('草稿编辑保留版本和重试键，发布后禁止编辑，创建不带旧版本', async () => {
  const calls = [],
    hooks = {},
    user = reactive({ permissions: ['billing:price:write'] })
  const mocks = {
    vue: {
      computed,
      reactive,
      ref,
      onBeforeUnmount: (fn) => {
        hooks.unmount = fn
      },
    },
    'vue-router': {
      onBeforeRouteLeave: (fn) => {
        hooks.leave = fn
      },
    },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/prices': {
      createPriceVersion: (...args) =>
        new Promise((resolve) => calls.push({ action: 'create', args, resolve })),
      updatePriceVersion: (...args) =>
        new Promise((resolve, reject) => calls.push({ action: 'update', args, resolve, reject })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/usePriceVersionEditor.js', import.meta.url),
      'utf8'
    ),
    { context }
  )
  await module.link((name) =>
    name === '@/utils/priceVersion'
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
  const state = module.namespace.usePriceVersionEditor(() => {})
  state.start({ id: '5' }, { id: '8', status: 'published' })
  assert.equal(state.open.value, false)
  const original = {
    id: '8',
    status: 'draft',
    revision: '12',
    items: form().items,
    sourceIds: ['9'],
    calculationScale: 10,
  }
  state.start({ id: '5' }, original)
  state.form.items[0].unitPrice = '2.0000000001'
  assert.equal(original.items[0].unitPrice, '0.0000000001')
  state.formRef.value = { validate: async () => true }
  const flush = () => new Promise((resolve) => setImmediate(resolve))
  const first = state.submit()
  await flush()
  assert.equal(hooks.leave(), false)
  assert.equal(calls[0].args[1].revision, '12')
  assert.equal(calls[0].args[1].priceBookId, undefined)
  calls[0].reject(new Error('网络中断'))
  await first
  const retry = state.submit()
  await flush()
  assert.equal(calls[1].args[2], calls[0].args[2])
  calls[1].resolve({})
  await retry
  state.start({ id: '9007199254740993' })
  const create = state.submit()
  await flush()
  assert.equal(calls[2].args[0].priceBookId, '9007199254740993')
  assert.equal(calls[2].args[0].revision, undefined)
  calls[2].resolve({})
  await create
  hooks.unmount()
})
