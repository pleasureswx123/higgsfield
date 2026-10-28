import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, ref, reactive, watch, effectScope } from 'vue'
import { randomUUID } from 'node:crypto'

test('路由切换隔离迟到响应，失败重试沿用幂等键且撤权清空', async () => {
  const hooks = {}, reads = [], writes = [], user = reactive({ permissions: ['provider:route'] })
  const context = createContext({ AbortController, crypto: { randomUUID } })
  const utils = new SourceTextModule(await readFile(new URL('../../src/utils/routing.js', import.meta.url), 'utf8'), { context })
  await utils.link(() => {}); await utils.evaluate()
  const mocks = {
    vue: { computed, ref, watch, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: () => {} },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/routing': {
      getRouting: (id, signal) => new Promise(resolve => reads.push({ id, signal, resolve })),
      saveRouting: (id, data, key) => new Promise((resolve, reject) => writes.push({ id, data, key, resolve, reject })),
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useRouting.js', import.meta.url), 'utf8'), { context })
  await module.link(name => name === '@/utils/routing' ? utils : new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useRouting())
  state.projectId.value = '1'; const first = state.load()
  state.projectId.value = '2'; const second = state.load()
  assert.equal(reads[0].signal.aborted, true)
  reads[0].resolve({ data: { revision: '9', routes: [] } }); await first
  assert.equal(state.revision.value, '')
  reads[1].resolve({ data: { revision: '1', routes: [] } }); await second
  state.formRef.value = { validate: async () => true }
  const failed = state.save(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(hooks.leave(), false)
  writes[0].reject(new Error('连接中断')); await failed
  const retry = state.save(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(writes[0].key, writes[1].key)
  user.permissions = []
  writes[1].resolve({ data: { revision: '2', routes: [] } }); await retry
  assert.equal(state.revision.value, '')
  assert.equal(state.message.value, '')
  assert.equal(hooks.leave(), true)
  user.permissions = ['provider:route']
  state.projectId.value = '3'
  const third = state.load()
  reads[2].resolve({ data: { revision: '3', routes: [] } }); await third
  const oldSave = state.save(); await new Promise(resolve => setImmediate(resolve))
  state.projectId.value = '4'
  writes[2].reject(new Error('项目3保存失败')); await oldSave
  assert.equal(state.error.value, '')
  assert.equal(state.message.value, '')
  // 校验期间切换目标也不能使用新上下文发送旧操作。
  const fourth = state.load()
  reads[3].resolve({ data: { revision: '4', routes: [] } }); await fourth
  let validated
  state.formRef.value = { validate: () => new Promise(resolve => { validated = resolve }) }
  const validating = state.save()
  state.projectId.value = '5'
  validated(true); await validating
  assert.equal(writes.length, 3)
  scope.stop()
})
