const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

function harness(refreshError) {
  const exports = {}, calls = [], hooks = {}, identity = vue.ref('1')
  const task = vue.ref({ id: '1', revision: '8', allowedActions: ['generation:cancel'] })
  const auth = vue.reactive({ token: 'test-token', user: { permissions: ['*:*:*'] } })
  let refreshed = 0, keys = 0
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useGenerationCancel.ts'), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  runInNewContext(compiled, { exports, Error, AbortController, crypto: { randomUUID: () => String(++keys) },
    require: name => name === 'vue' ? { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn } } : name === '@/stores/auth' ? { useAuthStore: () => auth } : {
      cancelGeneration: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
    } })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useGenerationCancel(() => identity.value, () => task.value, async () => {
    refreshed++
    if (refreshError) throw refreshError
  }))
  return { state, identity, task, calls, auth, hooks, refreshed: () => refreshed, cleanup() { hooks.unmount(); scope.stop() } }
}

test('网络失败保留原版本、原因和幂等键，实时状态变化后仍可确认结果', async () => {
  const h = harness()
  const first = h.state.submit()
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  h.calls[0].reject(Object.assign(new Error('网络中断'), { code: 0 }))
  await first
  assert.equal(h.state.retryable.value, true)
  h.task.value = { id: '1', revision: '9', allowedActions: [] }
  h.state.reason.value = '变更原因'
  const retry = h.state.submit()
  assert.deepEqual(h.calls[1].args.slice(0, 3), h.calls[0].args.slice(0, 3))
  h.calls[1].resolve({})
  await retry
  assert.equal(h.refreshed(), 1)
  assert.equal(h.state.retryable.value, false)
  h.cleanup()
})

test('明确冲突刷新任务，切换身份后忽略迟到结果', async () => {
  const h = harness()
  const first = h.state.submit()
  h.calls[0].reject(Object.assign(new Error('版本已变化'), { code: 409 }))
  await first
  assert.equal(h.refreshed(), 1)
  assert.equal(h.state.retryable.value, false)
  const next = h.state.submit()
  assert.notEqual(h.calls[1].args[2], h.calls[0].args[2])
  h.identity.value = '2'
  await vue.nextTick()
  h.calls[1].resolve({})
  await next
  assert.equal(h.refreshed(), 1)
  assert.equal(h.state.pending.value, false)
  assert.equal(h.state.error.value, '')
  h.cleanup()
})

test('原取消仍在处理中时冻结原请求，不能用新原因或版本重新取消', async () => {
  const h = harness()
  const first = h.state.submit()
  h.calls[0].reject(Object.assign(new Error('处理中'), { code: 601, errorCode: 'IDEMPOTENCY_IN_PROGRESS' }))
  await first
  assert.equal(h.state.retryable.value, true)
  assert.equal(h.refreshed(), 0)
  h.state.reason.value = '后来修改的原因'
  h.task.value = { id: '1', revision: '99', allowedActions: [] }
  const retry = h.state.submit()
  assert.deepEqual(h.calls[1].args.slice(0, 3), h.calls[0].args.slice(0, 3))
  h.calls[1].resolve({})
  await retry
  assert.equal(h.state.retryable.value, false)
  h.cleanup()
})

test('取消已确认但刷新失败，不显示原取消结果未知或重复刷新', async () => {
  const h = harness(new Error('刷新失败'))
  const first = h.state.submit()
  h.calls[0].resolve({})
  await first
  assert.equal(h.refreshed(), 1)
  assert.equal(h.state.retryable.value, false)
  assert.equal(h.state.pending.value, false)
  assert.equal(h.state.error.value, '刷新失败')
  h.cleanup()
})


test('退出登录立即中止请求，迟到结果不刷新详情', async () => {
  const h = harness()
  const first = h.state.submit()
  h.auth.token = ''
  assert.equal(h.calls[0].args[3].aborted, true)
  assert.equal(h.state.pending.value, false)
  h.calls[0].resolve({})
  await first
  assert.equal(h.refreshed(), 0)
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  h.cleanup()
})

test('缓存页面隐藏时隔离迟到响应，返回后用原键确认', async () => {
  const h = harness()
  const first = h.state.submit()
  h.hooks.deactivate()
  assert.equal(h.calls[0].args[3].aborted, true)
  assert.equal(h.state.retryable.value, true)
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  h.calls[0].resolve({})
  await first
  assert.equal(h.refreshed(), 0)
  h.hooks.activate()
  const retry = h.state.submit()
  assert.deepEqual(h.calls[1].args.slice(0, 3), h.calls[0].args.slice(0, 3))
  assert.equal(h.calls[1].args[3].aborted, false)
  h.calls[1].resolve({})
  await retry
  assert.equal(h.refreshed(), 1)
  h.cleanup()
})
