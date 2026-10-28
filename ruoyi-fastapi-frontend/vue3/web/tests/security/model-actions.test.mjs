import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'

test('模型状态操作按权限和状态隔离，证据与修订保留，失败重试使用原请求键', async () => {
  const calls = [], hooks = {}, user = reactive({ permissions: ['model:verify'] })
  const version = ref({ id: '9007199254740993', revision: '10', status: 'draft' })
  let saved = 0
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { computed, reactive, ref, onBeforeUnmount: fn => { hooks.unmount = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/models': { changeModelVersionState: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useModelVersionActions.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const state = module.namespace.useModelVersionActions(() => version.value, () => { saved++ })
  assert.equal(state.actions.value.join(','), 'verify')
  state.start('publish'); assert.equal(state.open.value, false)
  state.start('verify')
  state.formRef.value = { validate: async () => true }
  Object.assign(state.form, { reason: ' 已审阅 ', verificationRef: '证据/record-1' })
  const first = state.submit()
  await state.submit(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls.length, 1)
  assert.equal(hooks.leave(), false)
  assert.equal(calls[0].args[0], version.value.id)
  assert.equal(calls[0].args[1], 'verify')
  assert.equal(calls[0].args[2].revision, '10')
  assert.equal(calls[0].args[2].verificationRef, '证据/record-1')
  calls[0].reject(new Error('响应丢失')); await first
  const retry = state.submit(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls[1].args[3], calls[0].args[3])
  calls[1].resolve({}); await retry
  assert.equal(saved, 1)
  user.permissions = ['model:publish']
  version.value.status = 'verified'
  assert.equal(state.actions.value.join(','), 'publish,disable')
  version.value.status = 'published'
  assert.equal(state.actions.value.join(','), 'disable')
  version.value.status = 'disabled'
  assert.equal(state.actions.value.length, 0)
  hooks.unmount()
})
