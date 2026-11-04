const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(write) {
  const exports = {}, hooks = {}, updates = vue.reactive({ orderLocked: false, revision: 0, notify() { this.revision++ } })
  const auth = vue.reactive({ token: 'one', user: { user: { userId: 1 } } })
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjectOrder.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, crypto: require('node:crypto').webcrypto, require(id) {
      if (id === 'vue') return { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/stores/projectUpdates') return { useProjectUpdatesStore: () => updates }
      if (id === 'element-plus') return { ElMessage: { error() {}, info() {} } }
      if (id === '@/api/client') return { ApiError: class extends Error {} }
      return { putProjectOrder: write }
    },
  })
  const rows = vue.ref([{ id: '1', preference: { revision: '2', isPinned: true } }, { id: '2' }, { id: '3' }])
  const scope = vue.effectScope(), state = scope.run(() => exports.useProjectOrder(rows))
  return { state, rows, updates, auth, close() { hooks.unmount(); scope.stop() } }
}
test('拖动顺序整批保存，保留置顶边界和字符串修订', async () => {
  const calls = []
  const c = setup(async (...args) => calls.push(args))
  c.state.keyboard('2', -1); await tick()
  assert.equal(calls.length, 0)
  c.state.keyboard('3', -1); await tick()
  assert.equal(JSON.stringify(calls[0][0]), JSON.stringify([{ projectId: '1', revision: '2' }, { projectId: '3', revision: '0' }, { projectId: '2', revision: '0' }]))
  assert.equal(c.updates.orderLocked, false); assert.equal(c.updates.revision, 1)
  c.close()
})
test('结果未知时重试原快照及幂等键，禁止新排序', async () => {
  const calls = []
  const c = setup(async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('超时') })
  c.state.keyboard('3', -1); await tick()
  assert.equal(c.updates.orderLocked, true)
  c.state.keyboard('2', 1); await tick(); assert.equal(calls.length, 1)
  await c.state.save()
  assert.equal(calls[0][0], calls[1][0]); assert.equal(calls[0][1], calls[1][1])
  assert.equal(c.updates.orderLocked, false)
  c.close()
})
test('退出账号中断旧请求，迟到响应不刷新其他账号', async () => {
  let done, signal
  const c = setup((_items, _key, current) => { signal = current; return new Promise(resolve => { done = resolve }) })
  c.state.keyboard('3', -1)
  c.auth.token = ''; assert.equal(signal.aborted, true)
  done(); await tick(); assert.equal(c.updates.revision, 0)
  c.close()
})
