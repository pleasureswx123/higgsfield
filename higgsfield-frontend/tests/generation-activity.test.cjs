const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(list) {
  const exports = {}, hooks = {}, timers = new Map()
  const auth = vue.reactive({ token: 'test', user: { user: { userId: 1 }, permissions: [] } })
  let sequence = 0
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useGenerationActivity.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController,
    setTimeout(fn, ms) { const id = ++sequence; timers.set(id, { fn, ms }); return id },
    clearTimeout(id) { timers.delete(id) },
    require(id) {
      if (id === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/api/generations') return { listGenerations: list }
      throw new Error(id)
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useGenerationActivity(() => '2', () => true))
  return { state, auth, hooks, timers, close() { hooks.unmount(); scope.stop() } }
}
test('导航使用授权项目进行中总数，不把当前页条数当作总数；空闲时降低刷新频率', async () => {
  let total = 25
  const c = setup(async query => { assert.equal(query.scope, 'project'); assert.equal(query.category, 'active'); return { rows: [{}], total } })
  await tick(); assert.equal(c.state.count.value, 25); assert.equal([...c.timers.values()][0].ms, 5000)
  total = 0; await c.state.refresh(); assert.equal(c.state.count.value, 0); assert.equal([...c.timers.values()][0].ms, 30000)
  c.hooks.deactivate(); assert.equal(c.timers.size, 0); c.close()
})
test('退出账号后中止请求，迟到响应不能恢复计数或轮询', async () => {
  let finish, signal
  const c = setup((_query, current) => { signal = current; return new Promise(resolve => { finish = resolve }) })
  c.auth.token = ''; assert.equal(signal.aborted, true)
  finish({ total: 8 }); await tick()
  assert.equal(c.state.count.value, 0); assert.equal(c.timers.size, 0); c.close()
})
