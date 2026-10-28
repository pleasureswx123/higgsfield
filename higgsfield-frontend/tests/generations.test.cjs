const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

function harness() {
  const calls = [], hooks = {}, exported = {}
  const project = vue.ref(undefined), active = vue.ref(true), filter = vue.ref(undefined)
  const auth = vue.reactive({ token: 'one', user: { user: { userId: '1' }, permissions: ['generation:read'] } })
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useGenerations.ts'), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const mocks = {
    '@/utils/libraryWindow': dateHelper(),
    '@/stores/auth': { useAuthStore: () => auth },
    vue: { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn } },
    '@/api/generations': { listGenerations: (params, signal) => new Promise(resolve => { calls.push({ params, signal, resolve }) }) },
  }
  runInNewContext(compiled, { exports: exported, require: name => mocks[name], AbortController, Error })
  const scope = vue.effectScope()
  const state = scope.run(() => exported.useGenerations(() => project.value, () => active.value, () => filter.value))
  return { state, calls, hooks, project, filter, active, auth, cleanup() { hooks.unmount(); scope.stop() } }
}
const flush = async () => { await vue.nextTick(); await new Promise(resolve => setImmediate(resolve)) }

function dateHelper() {
  const exported = {}
  const source = readFileSync(require('node:path').join(__dirname, '../src/utils/libraryWindow.ts'), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  runInNewContext(compiled, { exports: exported, Error })
  return exported
}

test('任务日期按上海自然日含结束日，清除恢复无日期限制，非法日期不发请求', async () => {
  const h = harness()
  h.state.page.value = 3
  await flush()
  h.state.dates.value = ['2026-10-01', '2026-10-28']
  await flush()
  assert.equal(h.calls.at(-1).params.from, '2026-09-30T16:00:00.000Z')
  assert.equal(h.calls.at(-1).params.to, '2026-10-28T16:00:00.000Z')
  assert.equal(h.calls.at(-1).params.pageNum, 1)
  const pending = h.calls.at(-1), count = h.calls.length
  h.state.dates.value = ['2026-02-30', '2026-03-01']
  await flush()
  assert.equal(pending.signal.aborted, true)
  assert.equal(h.calls.length, count)
  assert.match(h.state.error.value, /日期/)
  pending.resolve({ rows: [{ id: 'old-date' }], total: 1 })
  await flush()
  assert.equal(h.state.rows.value.length, 0)
  h.state.dates.value = null
  await flush()
  assert.equal(h.calls.at(-1).params.from, undefined)
  assert.equal(h.calls.at(-1).params.to, undefined)
  assert.equal(h.state.error.value, '')
  h.cleanup()
})

test('我的生成按项目筛选仍保持mine范围，项目工作区范围不可被筛选替换', async () => {
  const h = harness()
  h.state.page.value = 3
  await flush()
  h.filter.value = '9007199254740993'
  await flush()
  assert.equal(h.calls.at(-1).params.scope, 'mine')
  assert.equal(h.calls.at(-1).params.projectId, '9007199254740993')
  assert.equal(h.calls.at(-1).params.pageNum, 1)
  h.project.value = '88'
  await flush()
  assert.equal(h.calls.at(-1).params.scope, 'project')
  assert.equal(h.calls.at(-1).params.projectId, '88')
  h.project.value = undefined
  h.filter.value = undefined
  await flush()
  assert.equal(h.calls.at(-1).params.scope, 'mine')
  assert.equal(h.calls.at(-1).params.projectId, undefined)
  h.cleanup()
})

test('筛选取消旧请求，迟到结果不能覆盖当前列表', async () => {
  const h = harness()
  assert.equal(h.calls[0].params.scope, 'mine')
  h.state.kind.value = 'video'
  await flush()
  assert.equal(h.calls[0].signal.aborted, true)
  h.calls[1].resolve({ rows: [{ id: 'new' }], total: 1 })
  await flush()
  h.calls[0].resolve({ rows: [{ id: 'old' }], total: 100 })
  await flush()
  assert.equal(h.state.rows.value[0].id, 'new')
  assert.equal(h.state.total.value, 1)
  h.cleanup()
})

test('切换项目重置页码，隐藏时暂停请求，重新激活刷新', async () => {
  const h = harness()
  h.state.page.value = 3
  await flush()
  h.project.value = '9007199254740993'
  await flush()
  assert.equal(h.state.page.value, 1)
  assert.equal(h.calls.at(-1).params.projectId, '9007199254740993')
  assert.equal(h.calls.at(-1).params.scope, 'project')
  h.active.value = false
  await flush()
  const count = h.calls.length
  assert.equal(h.calls.at(-1).signal.aborted, true)
  await h.state.refresh()
  assert.equal(h.calls.length, count)
  h.active.value = true
  await flush()
  assert.equal(h.calls.length, count + 1)
  h.hooks.deactivate()
  assert.equal(h.calls.at(-1).signal.aborted, true)
  h.hooks.activate()
  assert.equal(h.calls.length, count + 2)
  h.cleanup()
  assert.equal(h.calls.at(-1).signal.aborted, true)
})

test('账号与权限变化同步清空列表并隔离旧响应，退出后不再读取', async () => {
  const h = harness()
  h.calls[0].resolve({ rows: [{ id: 'account-one' }], total: 50 })
  await flush()
  h.state.page.value = 2
  await flush()
  const old = h.calls.at(-1)
  h.auth.token = 'two'
  assert.equal(h.state.rows.value.length, 0)
  assert.equal(h.state.total.value, 0)
  assert.equal(old.signal.aborted, true)
  await flush()
  assert.equal(h.calls.at(-1).params.pageNum, 1)
  old.resolve({ rows: [{ id: 'late-old-account' }], total: 50 })
  await flush()
  assert.equal(h.state.rows.value.length, 0)
  h.calls.at(-1).resolve({ rows: [{ id: 'account-two' }], total: 1 })
  await flush()
  h.auth.user.permissions = []
  assert.equal(h.state.rows.value.length, 0)
  assert.equal(h.state.total.value, 0)
  const permissionRead = h.calls.at(-1)
  h.auth.token = ''
  assert.equal(permissionRead.signal.aborted, true)
  const count = h.calls.length
  await h.state.refresh()
  assert.equal(h.calls.length, count)
  permissionRead.resolve({ rows: [{ id: 'revoked' }], total: 1 })
  await flush()
  assert.equal(h.state.rows.value.length, 0)
  h.cleanup()
})

test('隐藏与缓存停用清理卡片，未激活时权限变化不启动读取', async () => {
  const h = harness()
  h.calls[0].resolve({ rows: [{ id: 'old' }], total: 1 })
  await flush()
  h.active.value = false
  assert.equal(h.state.rows.value.length, 0)
  assert.equal(h.state.loading.value, false)
  await flush()
  h.hooks.deactivate()
  const count = h.calls.length
  h.auth.user.user.userId = '2'
  h.active.value = true
  await flush()
  assert.equal(h.calls.length, count)
  h.hooks.activate()
  assert.equal(h.calls.length, count + 1)
  h.cleanup()
  await h.state.refresh()
  assert.equal(h.calls.length, count + 1)
})
