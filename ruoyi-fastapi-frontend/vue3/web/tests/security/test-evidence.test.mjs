import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { ref, watch, reactive, effectScope, nextTick } from 'vue'

async function setup(api) {
  const hooks = {}, calls = [], props = reactive({ testId: '', credentialVersionId: '1', modelVersionId: '2', costCenterId: '3' })
  const context = createContext({ setInterval: fn => { hooks.tick = fn; return 1 }, clearInterval() {}, URL, navigator: { clipboard: { writeText: async () => {} } } })
  const mocks = { vue: { ref, watch, onMounted: fn => { hooks.mount = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } },
    '@/api/studio/credentials': { getCredentialTestPreview: async (...args) => { calls.push('preview'); return api.preview(...args) },
      getCredentialTestDetails: async id => { calls.push('details'); return api.details(id) }, getCredentialTestRuntime: async () => ({ data: { ready: true } }), getCredentialTestVideo: async () => new Blob() } }
  const mod = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useTestEvidence.js', import.meta.url), 'utf8'), { context })
  await mod.link(name => new SyntheticModule(Object.keys(mocks[name]), function () { for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value) }, { context }))
  await mod.evaluate()
  const scope = effectScope(), state = scope.run(() => mod.namespace.useTestEvidence(props, () => {}))
  hooks.mount()
  return { props, state, calls, hooks, close() { hooks.unmount(); scope.stop() } }
}
const flush = () => new Promise(resolve => setImmediate(resolve))

test('预览和刷新只读；测试完成后停止自动读取，仍可手动刷新', async () => {
  const h = await setup({ preview: async () => ({ data: { requestSource: 'preview' } }), details: async () => ({ data: { testState: '1', requestSource: 'saved' } }) })
  await flush()
  assert.equal(h.state.preview.value.requestSource, 'preview')
  await h.state.refresh()
  h.props.testId = '10'; await nextTick(); await flush()
  assert.equal(h.state.preview.value, undefined)
  assert.equal(h.state.detail.value.requestSource, 'saved')
  const count = h.calls.length
  h.hooks.tick(); await flush()
  assert.equal(h.calls.length, count)
  await h.state.refresh()
  assert.equal(h.calls.at(-1), 'details')
  h.close()
})

test('模型切换时忽略旧预览响应，不把预览当成实际发送记录', async () => {
  let finish
  const h = await setup({ preview: () => new Promise(resolve => { finish = resolve }), details: async () => ({ data: { testState: '0', request: { body: { model: 'new' } } } }) })
  h.props.testId = '11'; await nextTick()
  finish({ data: { request: { body: { model: 'old' } } } }); await flush()
  assert.equal(h.state.preview.value, undefined)
  assert.equal(h.state.detail.value.request.body.model, 'new')
  h.close()
})

test('等待中的测试自动读取响应，完成后停止轮询', async () => {
  let completed = false
  const h = await setup({ preview: async () => ({ data: { request: {} } }), details: async () => ({ data: completed ? { testState: '1', response: { result: 'ok' } } : { testState: '0' } }) })
  h.props.testId = '12'; await nextTick(); await flush()
  assert.equal(h.state.detail.value.testState, '0')
  completed = true
  h.hooks.tick(); await flush()
  assert.equal(h.state.detail.value.response.result, 'ok')
  const count = h.calls.length
  h.hooks.tick(); await flush()
  assert.equal(h.calls.length, count)
  h.close()
})
