import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { webcrypto } from 'node:crypto'
import { computed, reactive, ref, watch } from 'vue'

const row = { id: '8', revision: '3', state: 'draft', versionNo: 2 }
const evidence = id => ({ id, credentialVersionId: '8', state: 'passed', configHash: 'a'.repeat(64), result: { modelVerified: true } })
async function harness({ get = async id => ({ data: evidence(id) }), list = async () => ({ rows: [], total: 0 }), change = async () => {} } = {}) {
  const user = reactive({ permissions: ['*:*:*'] }), hooks = {}, calls = []
  let refreshed = 0
  const context = createContext({ crypto: webcrypto, Error, AbortController, window: { confirm: () => true, addEventListener() {}, removeEventListener() {} } })
  const mocks = {
    vue: { computed, reactive, ref, watch, onMounted: () => {}, onBeforeUnmount: fn => { hooks.unmount = fn }, onDeactivated: fn => { hooks.deactivate = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/credentials': { getCredentialTest: get, listCredentialTests: list, changeCredentialState: async (...args) => { calls.push(args); return change(...args) } },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useCredentialActivation.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const state = module.namespace.useCredentialActivation(async () => { refreshed++ })
  state.formRef.value = { validate: async () => true }
  state.start(row)
  return { state, hooks, calls, user, refreshed: () => refreshed }
}

test('启用携带固定版本和测试摘要，失败重试复用幂等键', async () => {
  const { state, calls } = await harness({ change: async () => { throw new Error('离线') } })
  state.form.testId = '11'
  await state.inspect()
  state.form.reason = '  测试通过  '
  await state.submit()
  await state.submit()
  assert.equal(calls.length, 2)
  assert.equal(calls[0][2].revision, '3')
  assert.equal(calls[0][2].testId, '11')
  assert.equal(calls[0][2].expectedConfigHash, 'a'.repeat(64))
  assert.equal(calls[0][2].reason, '测试通过')
  assert.equal(calls[0][3], calls[1][3])
  state.form.reason = '复核后启用'
  await state.submit()
  assert.notEqual(calls[1][3], calls[2][3])
})

test('旧查询响应和撤权后响应不能恢复启用资格', async () => {
  const deferred = []
  const { state, user } = await harness({ get: id => new Promise(resolve => deferred.push({ id, resolve })) })
  state.form.testId = '11'
  const first = state.inspect()
  state.form.testId = '12'
  const second = state.inspect()
  deferred[1].resolve({ data: evidence('12') })
  await second
  deferred[0].resolve({ data: evidence('11') })
  await first
  assert.equal(state.result.value.id, '12')
  assert.equal(state.eligible.value, true)
  user.permissions = []
  assert.equal(state.open.value, false)
  assert.equal(state.result.value, null)
  assert.equal(state.eligible.value, false)
})

test('异步校验期间不能重复提交或离开，成功刷新凭据', async () => {
  const { state, calls, hooks, refreshed } = await harness()
  state.form.testId = '11'
  await state.inspect()
  let resolve
  state.formRef.value = { validate: () => new Promise(done => { resolve = done }) }
  const pending = state.submit()
  await state.submit()
  state.close()
  assert.equal(state.open.value, true)
  assert.equal(hooks.leave(), false)
  resolve(true)
  await pending
  assert.equal(calls.length, 1)
  assert.equal(state.open.value, false)
  assert.equal(refreshed(), 1)
})

test('失败测试或其他凭据测试不能启用', async () => {
  for (const data of [{ ...evidence('11'), state: 'failed' }, { ...evidence('11'), credentialVersionId: '9' }]) {
    const { state, calls } = await harness({ get: async () => ({ data }) })
    state.form.testId = '11'
    await state.inspect()
    await state.submit()
    assert.equal(state.eligible.value, false)
    assert.equal(calls.length, 0)
  }
})

test('历史分页迟到响应不能覆盖新页，关闭后清空历史', async () => {
  const deferred = []
  const { state } = await harness({ list: (id, query) => new Promise(resolve => deferred.push({ id, query, resolve })) })
  state.history.page = 2
  const second = state.loadHistory()
  assert.equal(deferred[1].query.pageNum, 2)
  assert.equal(deferred[1].id, '8')
  deferred[1].resolve({ rows: [evidence('12')], total: 11 })
  await second
  deferred[0].resolve({ rows: [evidence('11')], total: 11 })
  await Promise.resolve()
  assert.equal(state.history.rows[0].id, '12')
  state.close()
  assert.equal(state.history.rows.length, 0)
  assert.equal(state.history.total, 0)
})

test('只读权限可以查看已启用版本的历史，但不能提交启用', async () => {
  const { state, user, calls } = await harness()
  user.permissions = ['credential:read']
  state.start({ ...row, state: 'active' })
  state.form.testId = '11'
  await state.inspect()
  assert.equal(state.open.value, true)
  assert.equal(state.result.value.id, '11')
  assert.equal(state.canActivate.value, false)
  await state.submit()
  assert.equal(calls.length, 0)
})

test('撤销账务权限立即移除金额，迟到响应也不能恢复金额', async () => {
  let resolve
  const detail = { ...evidence('11'), costVisibility: 'visible', cost: { amount: '1234567890123.1234567890' } }
  const { state, user } = await harness({ get: () => new Promise(done => { resolve = done }),
    list: async () => ({ rows: [detail], total: 1 }) })
  state.form.testId = '11'
  const pending = state.inspect()
  user.permissions = ['credential:read', 'credential:activate']
  resolve({ data: detail })
  await pending
  assert.equal(state.result.value.costVisibility, 'hidden')
  assert.equal('cost' in state.result.value, false)
  assert.equal(state.open.value, true)
  assert.equal(state.history.rows.some(row => 'cost' in row), false)
})
