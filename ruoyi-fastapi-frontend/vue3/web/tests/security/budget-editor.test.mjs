import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'

test('预算创建保留主体字符串与失败重试键，启停只发送版本和布尔状态', async () => {
  const calls = [], hooks = {}, user = reactive({ permissions: ['billing:budget'] })
  let saved = 0
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { computed, reactive, ref, onBeforeUnmount: fn => { hooks.unmount = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/budgets': {
      createBudget: (...args) => new Promise((resolve, reject) => calls.push({ kind: 'create', args, resolve, reject })),
      updateBudget: (...args) => new Promise(resolve => calls.push({ kind: 'update', args, resolve })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useBudgetEditor.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const state = module.namespace.useBudgetEditor(() => { saved++ })
  const flush = () => new Promise(resolve => setImmediate(resolve))
  state.start()
  state.formRef.value = { validate: async () => true }
  state.form.subjectType = 'user'
  state.form.subjectId = '9007199254740993'
  const first = state.submit()
  await state.submit(); await flush()
  state.close()
  assert.equal(state.open.value, true)
  assert.equal(hooks.leave(), false)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].args[0].subject.userId, '9007199254740993')
  assert.equal(calls[0].args[0].subject.projectId, undefined)
  calls[0].reject(new Error('响应丢失')); await first
  const retry = state.submit(); await flush()
  assert.equal(calls[0].args[1], calls[1].args[1])
  calls[1].resolve({}); await retry
  assert.equal(saved, 1)
  state.start({ id: '2', revision: '9', active: true })
  const toggle = state.submit(); await flush()
  assert.equal(calls[2].kind, 'update')
  assert.equal(calls[2].args[0], '2')
  assert.equal(JSON.stringify(calls[2].args[1]), '{"revision":"9","active":false}')
  calls[2].resolve({}); await toggle
  user.permissions = []
  state.start()
  assert.equal(state.open.value, false)
  await state.submit()
  assert.equal(calls.length, 3)
  hooks.unmount()
})
