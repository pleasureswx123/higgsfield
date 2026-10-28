import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch } from 'vue'
import { webcrypto } from 'node:crypto'
import { File } from 'node:buffer'
import { priceSourcePayload } from '../../src/utils/priceSource.js'
import { documentUploadItem } from '../../src/utils/documentUpload.js'
const form = () => ({
  sourceType: 'vendor_document',
  sourceUrl: 'https://example.com/prices',
  excerpt: '  原文  ',
  observedAt: '2026-01-01 08:00:00',
})

test('来源校验地址、依据和上海时间，不携带附件字段', () => {
  const now = Date.parse('2026-02-01T00:00:00Z'),
    result = priceSourcePayload(form(), now)
  assert.equal(Date.parse(result.observedAt), Date.parse('2026-01-01T00:00:00Z'))
  assert.equal(result.excerpt, '原文')
  assert.equal(result.uploadId, undefined)
  for (const url of [
    'javascript:alert(1)',
    'file:///tmp/a',
    'https://user:secret@example.com',
    'https://example.com/a b',
    '',
  ])
    assert.throws(() => priceSourcePayload({ ...form(), sourceUrl: url }, now))
  assert.equal(
    priceSourcePayload({ ...form(), sourceType: 'manual_confirmation', sourceUrl: '' }, now)
      .sourceUrl,
    null
  )
  assert.throws(() => priceSourcePayload({ ...form(), excerpt: '  ' }, now))
  assert.throws(() => priceSourcePayload(form(), Date.parse('2025-01-01T00:00:00Z')), /当前时间/)
  assert.equal(priceSourcePayload({ ...form(), sourceUrl: '', uploadId: '123' }, now).uploadId, '123')
})

test('来源登记失败保留输入与请求键，成功返回可绑定ID', async () => {
  const calls = [],
    hooks = {},
    user = reactive({ permissions: ['billing:price:write'] })
  const context = createContext({ crypto: webcrypto, AbortController })
  const mocks = {
    vue: {
      computed,
      reactive,
      ref,
      watch,
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
    '@/utils/priceSource': { priceSourcePayload },
    '@/api/studio/documentUploads': {},
    '@/utils/documentUpload': { documentUploadItem, uploadDocument: async () => '123' },
    '@/api/studio/prices': {
      createPriceSource: (...args) =>
        new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/usePriceSourceEditor.js', import.meta.url),
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
  let saved
  const state = module.namespace.usePriceSourceEditor((value) => {
    saved = value
  })
  state.start()
  Object.assign(state.form, form())
  state.formRef.value = { validate: async () => true }
  const flush = () => new Promise((resolve) => setImmediate(resolve))
  const first = state.submit()
  await flush()
  assert.equal(hooks.leave(), false)
  calls[0].reject(new Error('网络失败'))
  await first
  assert.equal(state.form.excerpt, '  原文  ')
  const retry = state.submit()
  await flush()
  assert.equal(calls[1].args[1], calls[0].args[1])
  calls[1].resolve({ data: { id: '9007199254740993' } })
  await retry
  assert.equal(saved.id, '9007199254740993')
  state.start()
  Object.assign(state.form, form(), { sourceUrl: '' })
  state.selectFile(new File(['证据原文'], '证据.txt'))
  await state.submit()
  assert.equal(calls.length, 2)
  await state.upload()
  assert.equal(state.form.uploadId, '123')
  const attached = state.submit()
  await flush()
  assert.equal(calls[2].args[0].uploadId, '123')
  calls[2].resolve({ data: { id: '10' } })
  await attached
  state.start()
  assert.equal(state.form.uploadId, '')
  user.permissions = []
  await state.submit()
  assert.equal(calls.length, 3)
  hooks.unmount()
})
