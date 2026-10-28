const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
function setup(overrides = {}) {
  const exports = {}, hooks = {}, saves = [], routes = [], auth = vue.reactive({ token: 'one' })
  const api = {
    getProjects: async () => ({ rows: [], total: 0 }),
    readBrief: async () => ({ data: { allowedActions: ['generation:create'] } }),
    saveCreationDraft: async (...args) => { saves.push(args); return { data: { id: '9007199254740993' } } },
    ...overrides,
  }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useHomeCreation.ts'), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, crypto: { randomUUID },
    window: { addEventListener: (name, fn) => { hooks[name] = fn }, removeEventListener: name => { delete hooks[name] } },
    require(name) {
      if (name === 'element-plus') return { ElMessageBox: { confirm: overrides.confirm || (async () => {}) } }
      if (name === 'vue') return { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onActivated: fn => { hooks.activate = fn } }
      if (name === 'vue-router') return { useRouter: () => ({ push: async route => { assert.equal(hooks.leave(), true); routes.push(route) } }), onBeforeRouteLeave: fn => { hooks.leave = fn } }
      if (name === '@/stores/auth') return { useAuthStore: () => auth }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useHomeCreation(overrides.inline ?? false))
  return { state, saves, routes, auth, hooks, close: () => { hooks.unmount(); scope.stop() } }
}
test('首页描述保存为无模型草稿，保留视频类型与正文，路由只携带草稿ID', async () => {
  const { state: s, saves, routes, close } = setup()
  s.prompt.value = ' 夜色中的车站\n记者入场 '; s.mode.value = 'video'
  await s.choose({ id: '12' })
  assert.equal(saves.length, 1)
  assert.equal(saves[0][0], null); assert.equal(saves[0][1], '12'); assert.equal(saves[0][2], 'video')
  assert.equal(saves[0][3].modelVersionId, null)
  assert.equal(saves[0][3].prompt.content[0].content[0].text, s.prompt.value)
  assert.equal(routes[0].query.draft, '9007199254740993'); assert.equal(routes[0].query.tab, 'creation')
  assert.equal(routes[0].query.prompt, undefined); close()
})
test('响应丢失重试同一草稿请求使用相同幂等键，修改内容生成新键', async () => {
  const calls = []
  const { state: s, close } = setup({ saveCreationDraft: async (...args) => { calls.push(args); throw new Error('断网') } })
  s.prompt.value = '描述'; await s.choose({ id: '12' }); await s.choose({ id: '12' })
  assert.equal(calls[0][4], calls[1][4]); assert.equal(s.prompt.value, '描述')
  s.prompt.value = '新描述'; await s.choose({ id: '12' }); assert.notEqual(calls[1][4], calls[2][4]); close()
})
test('没有创作权限不保存，切换账号后旧请求不继续写入或跳转', async () => {
  const denied = setup({ readBrief: async () => ({ data: { allowedActions: [] } }) })
  denied.state.prompt.value = '描述'; await denied.state.choose({ id: '12' })
  assert.equal(denied.saves.length, 0); assert.ok(denied.state.error.value); denied.close()
  let resolve
  const current = setup({ readBrief: () => new Promise(done => { resolve = done }) })
  current.state.prompt.value = '敏感描述'; const pending = current.state.choose({ id: '12' })
  assert.equal(current.hooks.leave(), false)
  current.auth.token = 'two'; await vue.nextTick()
  resolve({ data: { allowedActions: ['generation:create'] } }); await pending
  assert.equal(current.saves.length, 0); assert.equal(current.routes.length, 0)
  assert.equal(current.state.prompt.value, ''); current.close()
})
test('关闭项目选择后旧搜索结果不回填', async () => {
  let resolve, signal
  const { state: s, close } = setup({ getProjects: (params, current) => { signal = current; return new Promise(done => { resolve = done }) } })
  const pending = s.load(); s.close(); assert.equal(signal.aborted, true)
  resolve({ rows: [{ id: 'old' }], total: 1 }); await pending
  assert.equal(s.projects.value.length, 0); close()
})

test('未保存描述离开可取消，刷新受保护且卸载清理监听', async () => {
  const current = setup({ confirm: async () => { throw new Error('取消') } })
  assert.equal(current.hooks.leave(), true)
  current.state.prompt.value = '尚未保存的描述'
  assert.equal(await current.hooks.leave(), false)
  assert.equal(current.state.prompt.value, '尚未保存的描述')
  let prevented = false
  const event = { preventDefault: () => { prevented = true } }
  current.hooks.beforeunload(event)
  assert.equal(prevented, true)
  assert.equal(event.returnValue, '')
  current.hooks.deactivate(); prevented = false
  current.hooks.beforeunload(event); assert.equal(prevented, false)
  current.hooks.activate()
  current.hooks.beforeunload(event); assert.equal(prevented, true)
  current.close()
  assert.equal(current.hooks.beforeunload, undefined)
})

test('确认离开后放行，旧会话的确认不能放行新会话', async () => {
  let resolve
  const current = setup({ confirm: () => new Promise(done => { resolve = done }) })
  current.state.prompt.value = '描述'
  const first = current.hooks.leave(); resolve(); assert.equal(await first, true)
  const stale = current.hooks.leave()
  current.auth.token = 'new-session'; await vue.nextTick()
  resolve(); assert.equal(await stale, false)
  current.close()
})

test('切换账号立即重置，旧请求完成不能解除新账号保存锁', async () => {
  const pending = []
  const current = setup({ readBrief: () => new Promise(done => { pending.push(done) }) })
  current.state.prompt.value = '旧账号输入'; current.state.q.value = '旧项目'
  const old = current.state.choose({ id: '12' })
  current.auth.token = 'two'
  assert.equal(current.state.saving.value, false)
  assert.equal(current.state.prompt.value, '')
  assert.equal(current.state.q.value, '')
  current.state.prompt.value = '新账号输入'
  const fresh = current.state.choose({ id: '13' })
  pending[0]({ data: { allowedActions: ['generation:create'] } }); await old
  assert.equal(current.state.saving.value, true)
  assert.equal(current.saves.length, 0)
  assert.equal(current.state.prompt.value, '新账号输入')
  pending[1]({ data: { allowedActions: ['generation:create'] } }); await fresh
  assert.equal(current.saves.length, 1)
  assert.equal(current.saves[0][1], '13')
  current.close()
})

test('退出登录或隐藏首页后不读取项目或保存草稿', async () => {
  let reads = 0
  const current = setup({ getProjects: async () => { reads++; return { rows: [], total: 0 } } })
  current.hooks.deactivate(); current.state.prompt.value = '描述'
  await current.state.load(); await current.state.choose({ id: '12' })
  assert.equal(reads, 0); assert.equal(current.saves.length, 0)
  current.hooks.activate(); current.auth.token = ''; current.state.prompt.value = '描述'
  await current.state.load(); await current.state.choose({ id: '12' })
  assert.equal(reads, 0); assert.equal(current.saves.length, 0)
  current.close()
})

test('首页内嵌创作允许先选项目，不偷偷保存草稿或跳转', async () => {
  const current = setup({ inline: true })
  current.state.open()
  assert.equal(current.state.dialog.value, true)
  await current.state.choose({ id: '12', name: '创作项目' })
  assert.equal(current.state.selectedProject.value.id, '12')
  assert.equal(current.state.dialog.value, false)
  assert.equal(current.saves.length, 0)
  assert.equal(current.routes.length, 0)
  current.auth.token = 'two'
  assert.equal(current.state.selectedProject.value, null)
  current.close()
})
test('首页内嵌创作仍校验项目权限，拒绝未授权项目', async () => {
  const current = setup({ inline: true, readBrief: async () => ({ data: { allowedActions: [] } }) })
  await current.state.choose({ id: '12' })
  assert.equal(current.state.selectedProject.value, null)
  assert.ok(current.state.error.value)
  current.close()
})
