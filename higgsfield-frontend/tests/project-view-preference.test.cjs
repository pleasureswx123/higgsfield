const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code = code; this.errorCode = errorCode } }
const settings = () => ({ sort: 'created_desc', status: null, hidden: false, pinned: false, collectionId: null })
function setup(api = {}) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one', user: { permissions: [] } }), current = vue.reactive(settings()), applied = []
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjectViewPreference.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, Error, AbortController, crypto: { randomUUID }, require(id) {
      if (id === 'vue') return { ...vue, onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn }, onBeforeRouteUpdate: fn => { hooks.update = fn } }
      if (id === '@/api/client') return { ApiError }
      return { getProjectViewPreference: async () => ({ data: { revision: '1', settings: settings() } }), ...api }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useProjectViewPreference(() => current, value => applied.push(value)))
  return { state, hooks, auth, current, applied, close: () => { hooks.unmount(); scope.stop() } }
}
test('读取只加载修订，明确恢复才应用；请求期间的新筛选不被覆盖', async () => {
  const c = setup(); await c.state.load(); assert.equal(c.applied.length, 0)
  await c.state.load(true); assert.equal(c.applied.length, 1); c.close()
  let resolve
  const d = setup({ getProjectViewPreference: () => new Promise(done => { resolve = done }) })
  const pending = d.state.load(true); d.current.hidden = true
  resolve({ data: { revision: '2', settings: settings() } }); await pending
  assert.equal(d.applied.length, 0); assert.match(d.state.notice.value, /未覆盖/); d.close()
})
test('未知保存结果锁定原快照和键，缓存恢复后重试', async () => {
  const calls = []
  const c = setup({ saveProjectViewPreference: async (...args) => {
    calls.push(args); if (calls.length === 1) throw new Error('网络中断')
    return { data: { revision: '2' } }
  } })
  await c.state.load(); c.current.pinned = true; await c.state.save()
  assert.equal(c.hooks.leave(), false); c.current.pinned = false
  c.hooks.deactivate(); c.hooks.activate(); await c.state.save()
  assert.equal(calls[0][2], calls[1][2]); assert.equal(calls[1][0].pinned, true)
  assert.equal(c.state.uncertain.value, false); c.close()
})
test('修订冲突停止保存并要求重新读取，账号切换阻断迟到恢复', async () => {
  const c = setup({ saveProjectViewPreference: async () => { throw new ApiError('修订冲突', 601, 'REVISION_CONFLICT') } })
  await c.state.load(); await c.state.save(); assert.equal(c.state.ready.value, false); assert.equal(c.state.uncertain.value, false); c.close()
  let resolve
  const d = setup({ getProjectViewPreference: () => new Promise(done => { resolve = done }) })
  const pending = d.state.load(true); d.auth.token = ''
  resolve({ data: { revision: '3', settings: settings() } }); await pending
  assert.equal(d.applied.length, 0); assert.equal(d.state.ready.value, false); d.close()
})

test('408超时保留原日期快照和幂等键，阻止页内路由变化直到确认', async () => {
  const calls = []
  const c = setup({ saveProjectViewPreference: async (...args) => {
    calls.push(args)
    if (calls.length === 1) throw new ApiError('请求超时', 408)
    return { data: { revision: '2' } }
  } })
  await c.state.load(); c.current.dates = ['2024-02-29', '2024-03-01']; await c.state.save()
  assert.equal(c.state.ready.value, true); assert.equal(c.state.uncertain.value, true)
  assert.equal(c.hooks.update({ fullPath: '/project?tab=other' }, { fullPath: '/project?tab=assets' }), false)
  assert.equal(c.hooks.update({ fullPath: '/project' }, { fullPath: '/project' }), true)
  c.current.dates[0] = '2024-01-01'; await c.state.save()
  assert.equal(calls[1][0].dates[0], '2024-02-29'); assert.equal(calls[1][2], calls[0][2])
  assert.equal(c.hooks.update({ fullPath: '/other' }, { fullPath: '/project' }), true)
  c.close()
})

test('保存保留服务端其他白名单设置，嵌套数组快照不随外部修改变化', async () => {
  const folders = ['9007199254740993'], calls = []
  const c = setup({ getProjectViewPreference: async () => ({ data: { revision: '5', settings: { ...settings(), pinnedFolderIds: folders } } }),
    saveProjectViewPreference: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('未确认'); return { data: { revision: '6' } } } })
  await c.state.load(); await c.state.save(); folders.push('7'); await c.state.save()
  assert.equal(calls[1][0].pinnedFolderIds.length, 1)
  assert.equal(calls[1][0].pinnedFolderIds[0], '9007199254740993')
  assert.equal(calls[1][1], '5'); c.close()
})
