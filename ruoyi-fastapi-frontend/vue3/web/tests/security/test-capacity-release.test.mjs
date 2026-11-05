import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { webcrypto } from 'node:crypto'

test('未知测试释放须核查确认，响应丢失复用原请求，切换身份忽略迟到响应', async () => {
  const calls = [], user = reactive({ id: '1', token: 'mock', permissions: ['credential:test'] })
  let refreshes = 0
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { computed, reactive, ref, watch, onBeforeUnmount: () => {} },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/credentials': { releaseTestCapacity: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useTestCapacityRelease.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useTestCapacityRelease(() => '8', () => { refreshes++ }))
  state.form.reason = '供应商核查完毕'; state.form.evidenceRef = 'ticket:123'
  await state.submit()
  assert.equal(calls.length, 0)
  state.form.acknowledgeSupplierStopped = true
  const first = state.submit()
  calls[0].reject(new Error('响应丢失'))
  await first
  assert.equal(state.uncertain.value, true)
  state.form.reason = '修改不覆盖原始提交'
  const retry = state.submit()
  assert.equal(calls[1].args[2], calls[0].args[2])
  assert.equal(calls[1].args[1].reason, '供应商核查完毕')
  user.id = '2'
  calls[1].resolve({})
  await retry
  assert.equal(refreshes, 0)
  assert.equal(state.uncertain.value, false)
  user.permissions = []
  await state.submit()
  assert.equal(calls.length, 2)
  scope.stop()
})
