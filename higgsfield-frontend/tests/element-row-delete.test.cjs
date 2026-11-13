const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function setup(cancel = false, permission = true) {
  const calls = [], confirmations = [], hooks = [], cache = {}
  const auth = vue.reactive({ token: 'test' })
  let refreshed = 0
  function load(name) {
    if (cache[name]) return cache[name]
    const exports = {}; cache[name] = exports
    runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables', name + '.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
      exports, Error, crypto: { randomUUID: () => 'test-key' }, require(id) {
        if (id === 'vue') return { ...vue, onActivated() {}, onDeactivated() {}, onBeforeUnmount: fn => hooks.push(fn) }
        if (id === 'vue-router') return { onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} }
        if (id === '@/stores/auth') return { useAuthStore: () => auth }
        if (id === 'element-plus') return { ElMessageBox: { confirm: async (...args) => { confirmations.push(args); if (cancel) throw new Error('cancel') } } }
        if (id === '@/api/client') return { ApiError: class extends Error {} }
        if (id === '@/api/elements') return { recycleElement: async (...args) => { calls.push(args) } }
        if (id === './useBatchAction') return load('useBatchAction')
        throw new Error(id)
      },
    })
    return exports
  }
  const rows = vue.ref([{ id: '1', name: '测试元素', revision: '7', allowedActions: permission ? ['element:remove'] : [] }, { id: '2', name: '其他元素', revision: '9' }])
  const selected = vue.ref(['1']), scope = vue.effectScope()
  const state = scope.run(() => load('useElementBatchDelete').useElementBatchDelete(() => rows.value, () => true, async () => { refreshed++ }, selected, true))
  return { state, calls, confirmations, refreshed: () => refreshed, close() { hooks.forEach(fn => fn()); scope.stop() } }
}
test('单行删除只回收目标元素并携带修订，确认显示元素名称', async () => {
  const h = setup(); await h.state.execute()
  assert.equal(h.confirmations[0][1], '删除元素')
  assert.match(h.confirmations[0][0], /测试元素/)
  assert.deepEqual(h.calls[0], ['1', '7', false, 'test-key'])
  assert.equal(h.calls.length, 1); assert.equal(h.refreshed(), 1); h.close()
})
test('取消单行删除不发送请求、不刷新列表', async () => {
  const h = setup(true); await h.state.execute()
  assert.equal(h.calls.length, 0); assert.equal(h.refreshed(), 0); assert.equal(h.state.pending.value, false); h.close()
})
test('没有对象删除权限时不确认也不请求', async () => {
  const h = setup(false, false); await h.state.execute()
  assert.equal(h.confirmations.length, 0); assert.equal(h.calls.length, 0); h.close()
})
