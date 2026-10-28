const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(getProjects) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one', user: { permissions: ['project:read'] } })
  const route = vue.reactive({ query: { hidden: 'true', pinned: 'true', collectionId: '9007199254740993', page: '2' } })
  let replaced
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjects.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, require(id) {
      if (id === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === 'vue-router') return { useRoute: () => route, useRouter: () => ({ replace: async value => { replaced = value } }) }
      return { getProjects }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useProjects())
  return { state, hooks, auth, route, replaced: () => replaced, close: () => { hooks.unmount(); scope.stop() } }
}
test('导航筛选恢复路由并以字符串集合ID请求后端，切换筛选重置页码', async () => {
  let query
  const c = setup(async value => { query = value; return { rows: [], total: 0 } })
  c.hooks.activate(); await tick()
  assert.equal(query.hidden, true); assert.equal(query.pinned, true)
  assert.equal(query.collectionId, '9007199254740993'); assert.equal(query.pageNum, 2)
  c.state.hidden.value = false; c.state.pinned.value = false; c.state.applyFilters()
  assert.equal(c.replaced().query.page, '1'); assert.equal(c.replaced().query.hidden, undefined)
  assert.equal(c.replaced().query.collectionId, '9007199254740993')
  c.close()
})
test('退出与卸载使旧项目列表请求失效', async () => {
  let resolve, signal
  const c = setup((query, current) => { signal = current; return new Promise(done => { resolve = done }) })
  c.hooks.activate(); c.state.rows.value = [{ id: 'old' }]; c.state.total.value = 20
  c.auth.token = ''
  assert.equal(signal.aborted, true); assert.equal(c.state.rows.value.length, 0); assert.equal(c.state.total.value, 0)
  resolve({ rows: [{ id: 'late' }], total: 1 }); await tick()
  assert.equal(c.state.rows.value.length, 0)
  c.auth.token = 'two'; const latest = resolve; c.close()
  latest({ rows: [{ id: 'after-unmount' }], total: 1 }); await tick()
  assert.equal(c.state.rows.value.length, 0)
})

test('隐藏最后一项导致页码越界时保留筛选并回到最后有效页', async () => {
  const c = setup(async () => ({ rows: [], total: 20 }))
  c.hooks.activate(); await tick()
  assert.equal(c.replaced().query.page, '1')
  assert.equal(c.replaced().query.hidden, 'true')
  assert.equal(c.replaced().query.pinned, 'true')
  assert.equal(c.replaced().query.collectionId, '9007199254740993')
  assert.equal(c.state.total.value, 20)
  assert.equal(c.state.rows.value.length, 0)
  c.close()
})
