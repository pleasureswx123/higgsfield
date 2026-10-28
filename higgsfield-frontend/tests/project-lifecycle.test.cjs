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
    getProject: async () => ({ data: { id: '99', name: '项目', revision: '7', status: 'active' } }),
    readBrief: async () => ({ data: { allowedActions: ['project:archive'] } }),
    changeProjectLifecycle: async () => ({ data: { id: '99', revision: '8', status: 'archived' } }), ...overrides,
  }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjectLifecycle.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, crypto: { randomUUID }, require(id) {
      if (id === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn }, onBeforeRouteUpdate: fn => { hooks.update = fn } }
      if (id === '@/api/client') return { ApiError }
      if (id === 'element-plus') return { ElMessageBox: { confirm: overrides.confirm || (async () => {}) } }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useProjectLifecycle(() => changed++))
  state.form.value = { validate: async () => true }
  return { state, hooks, auth, changed: () => changed, close: () => { hooks.unmount(); scope.stop() } }
}

test('归档读取当前修订，校验后只提交一次，不确定结果保持同一请求', async () => {
  const calls = []
  const c = setup({ changeProjectLifecycle: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('断网'); return { data: { id: '99', status: 'archived', revision: '8' } } } })
  c.state.start({ id: '99', revision: '1' }, 'archive'); await tick()
  c.state.fields.reason = ' 项目完结 '; await c.state.save()
  assert.equal(calls[0][2].revision, '7'); assert.equal(calls[0][2].reason, '项目完结')
  assert.equal(c.state.uncertain.value, true); assert.equal(c.hooks.leave(), false)
  c.state.close(); assert.equal(c.state.open.value, true)
  c.state.fields.reason = '改变输入'; c.hooks.deactivate(); c.hooks.activate(); await c.state.save()
  assert.equal(calls[0][3], calls[1][3]); assert.equal(calls[1][2].reason, '项目完结')
  assert.equal(c.changed(), 1); assert.equal(c.state.open.value, false); c.close()
})

test('权限或状态变化阻止提交，恢复只接受归档项目', async () => {
  for (const [status, allowed, action, expected] of [['active', false, 'archive', false], ['pending_delete', true, 'archive', false], ['active', true, 'restore', false], ['archived', true, 'restore', true], ['paused', true, 'archive', true]]) {
    let writes = 0
    const c = setup({ getProject: async () => ({ data: { id: '99', revision: '7', status } }), readBrief: async () => ({ data: { allowedActions: allowed ? ['project:archive'] : [] } }), changeProjectLifecycle: async () => { writes++; return { data: { id: '99' } } } })
    c.state.start({ id: '99' }, action); await tick(); assert.equal(c.state.ready.value, expected)
    await c.state.save(); assert.equal(writes, expected ? 1 : 0); c.close()
  }
})

test('冲突要求重新核对并保留原因，处理中仍维持原意图', async () => {
  for (const code of ['REVISION_CONFLICT', 'IDEMPOTENCY_IN_PROGRESS']) {
    const c = setup({ changeProjectLifecycle: async () => { throw new ApiError('冲突', 601, code) } })
    c.state.start({ id: '99' }, 'archive'); await tick(); c.state.fields.reason = '保留原因'; await c.state.save()
    assert.equal(c.state.uncertain.value, code === 'IDEMPOTENCY_IN_PROGRESS')
    assert.equal(c.state.ready.value, code === 'IDEMPOTENCY_IN_PROGRESS')
    assert.equal(c.state.fields.reason, '保留原因'); c.close()
  }
})

test('账号切换取消请求，迟到提交不改变新账号页面', async () => {
  let resolve, signal
  const c = setup({ changeProjectLifecycle: (...args) => { signal = args[4]; return new Promise(done => { resolve = done }) } })
  c.state.start({ id: '99' }, 'archive'); await tick()
  const pending = c.state.save(); await tick()
  c.auth.token = 'two'; assert.equal(signal.aborted, true)
  resolve({ data: { id: '99', status: 'archived' } }); await pending
  assert.equal(c.changed(), 0); assert.equal(c.state.open.value, false); c.close()
})

test('重复点击只提交一次，验证等待中关闭不能发出写入', async () => {
  let resolve, writes = 0
  const c = setup({ changeProjectLifecycle: async () => { writes++; return { data: { id: '99' } } } })
  c.state.start({ id: '99' }, 'archive'); await tick()
  await Promise.all([c.state.save(), c.state.save()]); assert.equal(writes, 1)
  c.state.start({ id: '99' }, 'archive'); await tick()
  c.state.form.value = { validate: () => new Promise(done => { resolve = done }) }
  const pending = c.state.save(); c.state.close(); resolve(true); await pending
  assert.equal(writes, 1); c.close()
})

test('表单规则要求归档原因，恢复允许不填且两者限制长度', () => {
  const c = setup()
  function invalid(value) {
    let error
    c.state.rules.value.reason[0].validator({}, value, result => { error = result })
    return !!error
  }
  assert.equal(invalid('   '), true)
  assert.equal(invalid('完成制作'), false)
  assert.equal(invalid('字'.repeat(4001)), true)
  c.state.action.value = 'restore'
  assert.equal(invalid(''), false)
  c.close()
})

test('项目改名读取最新名称与修订，冲突后重读保留输入并发送专用字段', async () => {
  const calls = []; let revision = '7'
  const c = setup({ getProject: async () => ({ data: { id: '99', name: '服务端名称', revision, status: 'active' } }),
    readBrief: async () => ({ data: { allowedActions: ['project:manage'] } }),
    changeProjectLifecycle: async (...args) => { calls.push(args); if (calls.length === 1) throw new ApiError('冲突', 601, 'REVISION_CONFLICT'); return { data: { id: '99', name: args[2].name } } } })
  c.state.start({ id: '99', name: '旧名称' }, 'rename'); await tick()
  assert.equal(c.state.fields.name, '服务端名称')
  c.state.fields.name = ' 新项目名称 '; await c.state.save()
  assert.equal(c.state.ready.value, false); assert.equal(c.state.fields.name, ' 新项目名称 ')
  revision = '8'; await c.state.load(); assert.equal(c.state.fields.name, ' 新项目名称 ')
  await c.state.save()
  assert.equal(calls[1][1], 'rename'); assert.equal(calls[1][2].revision, '8')
  assert.equal(calls[1][2].name, '新项目名称'); assert.equal('reason' in calls[1][2], false)
  assert.notEqual(calls[0][3], calls[1][3]); assert.equal(c.changed(), 1); c.close()
})

test('归档权限不替代改名权限，暂停状态不能改名，名称校验不接受空白和控制字符', async () => {
  const c = setup(); c.state.start({ id: '99' }, 'rename'); await tick()
  assert.equal(c.state.ready.value, false)
  for (const name of ['', '  ', '非法\n名称', '字'.repeat(201)]) {
    let error
    c.state.rules.value.name[0].validator({}, name, result => { error = result })
    assert.ok(error)
  }
  c.close()
  const d = setup({ getProject: async () => ({ data: { id: '99', name: '项目', revision: '1', status: 'paused' } }), readBrief: async () => ({ data: { allowedActions: ['project:manage'] } }) })
  d.state.start({ id: '99' }, 'rename'); await tick(); assert.equal(d.state.ready.value, false); d.close()
})

test('暂停及恢复运行按管理权限和状态开放，暂停必须填写原因', async () => {
  for (const [action, status, allowed, ready] of [['pause', 'active', true, true], ['resume', 'paused', true, true], ['resume', 'archived', true, false], ['pause', 'paused', true, false], ['resume', 'paused', false, false]]) {
    const calls = []
    const c = setup({ getProject: async () => ({ data: { id: '99', name: '项目', revision: '4', status } }),
      readBrief: async () => ({ data: { allowedActions: allowed ? ['project:manage'] : ['project:archive'] } }),
      changeProjectLifecycle: async (...args) => { calls.push(args); return { data: { id: '99' } } } })
    c.state.start({ id: '99' }, action); await tick(); assert.equal(c.state.ready.value, ready)
    let error
    c.state.rules.value.reason[0].validator({}, '', result => { error = result })
    assert.equal(!!error, action === 'pause')
    c.state.fields.reason = '维护'; await c.state.save()
    assert.equal(calls.length, ready ? 1 : 0)
    if (ready) { assert.equal(calls[0][1], action); assert.equal(calls[0][2].revision, '4'); assert.equal(calls[0][2].reason, '维护') }
    c.close()
  }
})

test('未提交的名称或原因可取消离开，确认后关闭', async () => {
  for (const action of ['rename', 'archive']) {
    let accept = false
    const c = setup({ readBrief: async () => ({ data: { allowedActions: ['project:manage', 'project:archive'] } }),
      confirm: async () => { if (!accept) throw new Error('取消') } })
    c.state.start({ id: '99', name: '项目' }, action); await tick()
    assert.equal(c.hooks.leave(), true)
    if (action === 'rename') c.state.fields.name = '新名称'
    else c.state.fields.reason = '完结原因'
    assert.equal(await c.hooks.leave(), false)
    assert.equal(await c.hooks.update({ params: { id: '100' } }, { params: { id: '99' } }), false)
    assert.equal(c.hooks.update({ params: { id: '99' } }, { params: { id: '99' } }), true)
    await c.state.close(); assert.equal(c.state.open.value, true)
    c.hooks.deactivate(); c.hooks.activate(); await tick()
    assert.equal(action === 'rename' ? c.state.fields.name : c.state.fields.reason, action === 'rename' ? '新名称' : '完结原因')
    accept = true; await c.state.close(); assert.equal(c.state.open.value, false)
    c.close()
  }
})

test('旧账号的确认不能关闭新账号项目操作', async () => {
  let resolve
  const c = setup({ confirm: () => new Promise(done => { resolve = done }) })
  c.state.start({ id: '99' }, 'archive'); await tick(); c.state.fields.reason = '原因'
  const closing = c.state.close()
  c.auth.token = 'two'; c.state.start({ id: '99' }, 'archive'); await tick()
  resolve(); await closing
  assert.equal(c.state.open.value, true); c.close()
})
