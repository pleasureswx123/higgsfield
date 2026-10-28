const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code = code; this.errorCode = errorCode } }
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(overrides = {}) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one', user: { permissions: ['project:read'] } })
  let changed = 0
  const api = {
    getProjectPreference: async () => ({ data: { projectId: '99', revision: '0', isPinned: false, isHidden: false, collectionId: null, orderNum: 0 } }),
    getProjectCollections: async () => ({ rows: [{ id: '9007199254740993', name: '制作' }], hasNext: false }),
    putProjectPreference: async () => ({}), ...overrides,
  }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjectPreferenceEditor.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, crypto: { randomUUID }, require(id) {
      if (id === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn } }
      if (id === '@/api/client') return { ApiError }
      if (id === 'element-plus') return { ElMessageBox: { confirm: overrides.confirm || (async () => {}) } }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useProjectPreferenceEditor(() => changed++))
  state.form.value = { validate: async () => true }
  return { state, hooks, auth, changed: () => changed, close: () => { hooks.unmount(); scope.stop() } }
}
test('不确定结果保留快照与幂等键，缓存恢复后重试，不泄漏projectId字段', async () => {
  const calls = []
  const c = setup({ putProjectPreference: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('网络断开') } })
  c.state.start({ id: '99', name: '项目' }); await tick()
  c.state.fields.isPinned = true; await c.state.save()
  assert.equal(c.state.uncertain.value, true); assert.equal(c.hooks.leave(), false)
  c.state.close(); assert.equal(c.state.open.value, true)
  c.state.fields.isPinned = false
  c.hooks.deactivate(); c.hooks.activate(); await c.state.save()
  assert.equal(calls[0][2], calls[1][2]); assert.equal(calls[1][1].isPinned, true)
  assert.equal('projectId' in calls[1][1], false)
  assert.equal(c.changed(), 1); assert.equal(c.state.open.value, false); c.close()
})
test('明确修订冲突要求重新读取；处理中业务错误仍保留重试', async () => {
  for (const errorCode of ['REVISION_CONFLICT', 'IDEMPOTENCY_IN_PROGRESS']) {
    const c = setup({ putProjectPreference: async () => { throw new ApiError('冲突', 601, errorCode) } })
    c.state.start({ id: '99' }); await tick(); await c.state.save()
    assert.equal(c.state.uncertain.value, errorCode === 'IDEMPOTENCY_IN_PROGRESS')
    assert.equal(c.state.ready.value, errorCode === 'IDEMPOTENCY_IN_PROGRESS'); c.close()
  }
})
test('校验期间切换账号阻止写入，迟到读取不回填', async () => {
  let validated, resolve, writes = 0
  const c = setup({ putProjectPreference: async () => { writes++ } })
  c.state.start({ id: '99' }); await tick()
  c.state.form.value = { validate: () => new Promise(done => { validated = done }) }
  const saving = c.state.save(); c.auth.token = 'two'; validated(true); await saving
  assert.equal(writes, 0); assert.equal(c.state.open.value, false); c.close()
  const d = setup({ getProjectPreference: () => new Promise(done => { resolve = done }) })
  d.state.start({ id: '99' }); d.auth.token = 'two'
  resolve({ data: { revision: '9', isPinned: true } }); await tick()
  assert.equal(d.state.ready.value, false); assert.equal(d.state.fields.isPinned, false); d.close()
})

test('取消离开保留偏好修改，缓存恢复不覆盖输入，确认后关闭', async () => {
  let accept = false
  const c = setup({ confirm: async () => { if (!accept) throw new Error('取消') } })
  c.state.start({ id: '99' }); await tick()
  assert.equal(c.hooks.leave(), true)
  c.state.fields.orderNum = 42
  await c.state.close(); assert.equal(c.state.open.value, true)
  assert.equal(await c.hooks.leave(), false)
  c.hooks.deactivate(); c.hooks.activate(); await tick()
  assert.equal(c.state.fields.orderNum, 42)
  accept = true; await c.state.close()
  assert.equal(c.state.open.value, false); c.close()
})

test('旧会话的放弃确认不能关闭新会话弹窗', async () => {
  let resolve
  const c = setup({ confirm: () => new Promise(done => { resolve = done }) })
  c.state.start({ id: '99' }); await tick(); c.state.fields.isPinned = true
  const closing = c.state.close()
  c.auth.token = 'new'; c.state.start({ id: '100' }); await tick()
  resolve(); await closing
  assert.equal(c.state.open.value, true); assert.equal(c.state.target.value.id, '100')
  c.close()
})
