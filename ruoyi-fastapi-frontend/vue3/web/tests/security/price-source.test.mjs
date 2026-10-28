import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, ref, reactive, watch, effectScope } from 'vue'

test('来源仅查询绑定ID，切换、撤权及卸载阻断迟到证据', async () => {
  const calls = [], downloads = [], saved = [],
    hooks = {},
    user = reactive({ permissions: ['billing:price:read'] }),
    ids = ref(['1', '2'])
  const context = createContext({ AbortController })
  const mocks = {
    vue: {
      computed,
      ref,
      watch,
      onDeactivated: (fn) => {
        hooks.deactivate = fn
      },
      onBeforeUnmount: (fn) => {
        hooks.unmount = fn
      },
    },
    '@/store/modules/user': { default: () => user },
    'file-saver': { saveAs: (...args) => saved.push(args) },
    '@/api/studio/prices': {
      downloadPriceSource: (id, signal) =>
        new Promise((resolve, reject) => downloads.push({ id, signal, resolve, reject })),
      getPriceSource: (id, signal) =>
        new Promise((resolve, reject) => calls.push({ id, signal, resolve, reject })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/usePriceSource.js', import.meta.url),
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
  const scope = effectScope(),
    state = scope.run(() => module.namespace.usePriceSource(() => ids.value))
  await state.select('3')
  assert.equal(calls.length, 0)
  const one = state.select('1'),
    two = state.select('2')
  assert.equal(calls[0].signal.aborted, true)
  calls[0].resolve({ data: { id: '1', excerpt: '旧证据' } })
  await one
  assert.equal(state.source.value, undefined)
  calls[1].resolve({ data: { id: '2', excerpt: '<script>原文</script>' } })
  await two
  assert.equal(state.source.value.excerpt, '<script>原文</script>')
  state.source.value.attachment = { fileName: '报价.csv', byteSize: '20' }
  const download = state.download()
  downloads[0].resolve({ type: 'text/csv', size: 20 })
  await download
  assert.equal(saved.length, 1)
  assert.equal(saved[0][1], '报价.csv')
  const invalid = state.download()
  downloads[1].resolve({ type: 'application/json', size: 20 })
  await invalid
  assert.equal(saved.length, 1)
  assert.match(state.error.value, /下载失败/)
  const lateDownload = state.download()
  ids.value = ['4']
  assert.equal(downloads[2].signal.aborted, true)
  downloads[2].resolve({ type: 'text/csv', size: 20 })
  await lateDownload
  assert.equal(saved.length, 1)
  assert.equal(state.source.value, undefined)
  const revoked = state.select('4')
  user.permissions = []
  calls[2].resolve({ data: { id: '4' } })
  await revoked
  assert.equal(state.source.value, undefined)
  user.permissions = ['billing:price:read']
  const left = state.select('4')
  hooks.unmount()
  calls[3].reject(new Error('迟到失败'))
  await left
  assert.equal(state.error.value, '')
  assert.equal(state.loading.value, false)
  scope.stop()
})
