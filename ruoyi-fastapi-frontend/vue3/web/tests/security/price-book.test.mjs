import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'

test('价格簿登记保留规格ID、失败输入和幂等键，权限撤销后不可提交', async () => {
  const calls = [],
    hooks = {},
    user = reactive({ permissions: ['billing:price:write'] })
  const context = createContext({ crypto: webcrypto })
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
      createPriceBook: (...args) =>
        new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/usePriceBookEditor.js', import.meta.url),
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
  let saved = 0
  const state = module.namespace.usePriceBookEditor(() => {
    saved++
  })
  const flush = () => new Promise((resolve) => setImmediate(resolve))
  state.start('9007199254740993')
  state.formRef.value = { validate: async () => true }
  Object.assign(state.form, {
    name: ' 测试价格簿 ',
    purpose: 'procurement',
    accountId: '9007199254740995',
    currency: 'CNY',
  })
  const first = state.submit()
  await state.submit()
  await flush()
  assert.equal(calls.length, 1)
  assert.equal(hooks.leave(), false)
  assert.equal(calls[0].args[0].modelVariantId, '9007199254740993')
  assert.equal(calls[0].args[0].name, '测试价格簿')
  assert.equal(calls[0].args[0].accountId, '9007199254740995')
  calls[0].reject(new Error('响应丢失'))
  await first
  assert.equal(state.form.name, ' 测试价格簿 ')
  const retry = state.submit()
  await flush()
  assert.equal(calls[1].args[1], calls[0].args[1])
  calls[1].resolve({})
  await retry
  assert.equal(saved, 1)
  state.start('2')
  state.form.accountId = '999'
  const platform = state.submit()
  await flush()
  assert.equal(calls[2].args[0].accountId, null)
  calls[2].resolve({})
  await platform
  state.start('2')
  user.permissions = []
  await state.submit()
  assert.equal(calls.length, 3)
  hooks.unmount()
})
