import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'
import { emptyCapabilities, parseCapabilities } from '../../src/utils/modelCapabilities.js'

test('能力配置保留完整契约，拒绝非法JSON和不安全数字', () => {
  const config = emptyCapabilities()
  config.estimatePolicy = { kind: 'test', unitUpperBounds: { inputTokens: '123.45' } }
  assert.deepEqual(parseCapabilities(JSON.stringify(config)), config)
  for (const text of ['[]', 'null', '{}', '{', '{"parametersSchema":{},"referenceRules":{},"bad":9007199254740993}']) assert.throws(() => parseCapabilities(text))
})

test('草稿编辑保留完整配置及版本，已发布版本不可编辑，重试复用请求键', async () => {
  const hooks = {}, calls = [], user = reactive({ permissions: ['model:write'] })
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { computed, reactive, ref, onBeforeUnmount: fn => { hooks.unmount = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/utils/modelCapabilities': { emptyCapabilities, parseCapabilities },
    '@/api/studio/models': {
      createModelVersion: (...args) => new Promise(resolve => calls.push({ kind: 'create', args, resolve })),
      updateModelVersion: (...args) => new Promise((resolve, reject) => calls.push({ kind: 'update', args, resolve, reject })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useModelVersionEditor.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () { for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value) }, { context }))
  await module.evaluate()
  let saved = 0
  const state = module.namespace.useModelVersionEditor(() => { saved++ })
  const model = { id: '9007199254740993' }, version = { id: '2', revision: '12', status: 'published', region: 'cn', gatewayAlias: 'image-alias', capabilities: emptyCapabilities() }
  state.start(model, version); assert.equal(state.open.value, false)
  version.status = 'draft'; state.start(model, version)
  state.formRef.value = { validate: async () => true }
  const first = state.submit(); await state.submit(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls.length, 1)
  assert.equal(hooks.leave(), false)
  assert.equal(calls[0].args[1].revision, '12')
  assert.equal(calls[0].args[1].region, undefined)
  assert.equal(calls[0].args[1].underlyingModelId, null)
  assert.deepEqual(calls[0].args[1].capabilities, version.capabilities)
  calls[0].reject(new Error('响应丢失')); await first
  const retry = state.submit(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls[1].args[2], calls[0].args[2])
  calls[1].resolve({}); await retry
  state.start(model); state.form.gatewayAlias = 'new'; state.form.region = 'cn'
  const creation = state.submit(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls[2].kind, 'create'); assert.equal(calls[2].args[0], model.id)
  assert.equal(calls[2].args[1].schemaVersion, 1)
  assert.equal(calls[2].args[1].revision, undefined)
  calls[2].resolve({}); await creation
  assert.equal(saved, 2)
  hooks.unmount()
})
