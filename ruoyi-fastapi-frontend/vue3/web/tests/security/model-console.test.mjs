import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { reactive, ref, watch, effectScope } from 'vue'

test('模型切换隔离旧版本及规格，离开页面清除配置', async () => {
  const hooks = {}, versions = [], details = [], variants = []
  const context = createContext({ AbortController })
  const mocks = {
    vue: { reactive, ref, watch, onMounted: fn => { hooks.mount = fn }, onActivated: () => {}, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: () => {} },
    '@/api/studio/models': {
      listModels: async () => ({ rows: [], total: 0 }),
      listModelVersions: (id, params, signal) => new Promise(resolve => versions.push({ id, signal, resolve })),
      getModelVersion: (id, signal) => new Promise(resolve => details.push({ id, signal, resolve })),
      listModelVariants: (id, params, signal) => new Promise(resolve => variants.push({ id, signal, resolve })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useModels.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useModels())
  hooks.mount()
  const one = state.selectModel({ id: '1' }), two = state.selectModel({ id: '2' })
  assert.equal(versions[0].signal.aborted, true)
  versions[0].resolve({ rows: [{ id: '10' }], total: 1 }); await one
  versions[1].resolve({ rows: [{ id: '20' }], total: 1 }); await two
  const detail = state.selectVersion({ id: '20' })
  details[0].resolve({ data: { id: '20', capabilities: { mode: 'test' } } })
  await new Promise(resolve => setImmediate(resolve))
  const next = state.selectModel({ id: '3' })
  assert.equal(variants[0].signal.aborted, true)
  variants[0].resolve({ rows: [{ id: '200' }], total: 1 }); await detail
  assert.equal(state.version.value, undefined)
  assert.equal(state.variants.rows.length, 0)
  hooks.deactivate()
  versions[2].resolve({ rows: [{ id: '30' }], total: 1 }); await next
  assert.equal(state.versions.rows.length, 0)
  scope.stop()
})
