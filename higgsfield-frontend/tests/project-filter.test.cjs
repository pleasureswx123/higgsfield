const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const path = require('node:path')
const ts = require('typescript')
const vue = require('vue')
const flush = () => vue.nextTick()
function harness() {
  const auth = vue.reactive({ token: 'one', user: { user: { userId: '1' }, permissions: [] } })
  const enabled = vue.ref(true), selected = vue.ref('old'), calls = [], hooks = {}, exported = {}
  const source = readFileSync(path.join(__dirname, '../src/composables/useProjectFilter.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const mocks = {
    vue: { ...vue, onActivated: fn => hooks.activate = fn, onDeactivated: fn => hooks.deactivate = fn, onBeforeUnmount: fn => hooks.unmount = fn },
    '@/stores/auth': { useAuthStore: () => auth },
    '@/api/projects': { getProjects: (params, signal) => new Promise((resolve, reject) => calls.push({ params, signal, resolve, reject })) },
  }
  runInNewContext(code, { exports: exported, require: name => mocks[name], AbortController, Error })
  const scope = vue.effectScope()
  const state = scope.run(() => exported.useProjectFilter(() => enabled.value, () => selected.value = null))
  return { state, auth, enabled, selected, calls, hooks, cleanup() { hooks.unmount(); scope.stop() } }
}
test('项目筛选按需读取，搜索与分页取消旧请求，不限制为活跃项目', async () => {
  const h = harness()
  assert.equal(h.calls.length, 0)
  h.state.opened.value = true
  await flush()
  assert.equal(h.calls[0].params.status, undefined)
  assert.equal(h.calls[0].params.pageSize, 10)
  h.state.page.value = 2
  await flush()
  assert.equal(h.calls[0].signal.aborted, true)
  h.state.q.value = ' 测试项目 '
  h.state.search()
  await flush()
  assert.equal(h.calls.at(-1).params.q, '测试项目')
  assert.equal(h.calls.at(-1).params.pageNum, 1)
  h.calls.at(-1).resolve({ rows: [{ id: '9007199254740993', name: '同名项目' }], total: 1 })
  await flush()
  h.calls[0].resolve({ rows: [{ id: 'stale' }], total: 99 })
  await flush()
  assert.equal(h.state.rows.value[0].id, '9007199254740993')
  h.cleanup()
})
test('授权变化清除选择与候选，隐藏和停用禁止旧响应恢复', async () => {
  const h = harness()
  h.state.opened.value = true
  await flush()
  h.auth.token = 'two'
  assert.equal(h.selected.value, null)
  assert.equal(h.state.opened.value, false)
  assert.equal(h.calls[0].signal.aborted, true)
  h.calls[0].resolve({ rows: [{ id: 'old' }], total: 1 })
  await flush()
  assert.equal(h.state.rows.value.length, 0)
  h.state.opened.value = true
  await flush()
  h.enabled.value = false
  assert.equal(h.calls.at(-1).signal.aborted, true)
  await flush()
  h.hooks.deactivate()
  h.enabled.value = true
  h.state.opened.value = true
  await flush()
  const count = h.calls.length
  await h.state.load()
  assert.equal(h.calls.length, count)
  h.cleanup()
})
