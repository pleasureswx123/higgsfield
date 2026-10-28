const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const { randomUUID } = require('node:crypto')
class ApiError extends Error { constructor(message, code) { super(message); this.code = code } }
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(api, kind = 'useProjectMembers', confirm = async () => {}) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one' })
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjectWorkspace.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, crypto: { randomUUID }, window: { addEventListener() {}, removeEventListener() {} }, require(id) {
      if (id === 'vue') return { ...vue, onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/api/client') return { ApiError }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn }, onBeforeRouteUpdate: fn => { hooks.update = fn } }
      if (id === 'element-plus') return { ElMessageBox: { confirm } }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports[kind]('99'))
  return { state, hooks, auth, close: () => { hooks.unmount(); scope.stop() } }
}

test('账号切换立即清除成员角色总数并阻断旧请求回填', async () => {
  let resolve, signal
  const c = setup({ readMembers: (id, page, status, current) => { signal = current; return new Promise(done => { resolve = done }) }, readRoles: async () => ({ data: { items: [{ id: 'role' }] } }) })
  c.state.members.value = [{ userId: 'old' }]; c.state.total.value = 20
  const pending = c.state.load()
  c.auth.token = 'two'
  assert.equal(signal.aborted, true)
  assert.equal(c.state.total.value, 0)
  assert.equal(c.state.members.value.length, 0)
  resolve({ rows: [{ userId: 'late' }], total: 1 }); await pending
  assert.equal(c.state.roles.value.length, 0)
  assert.equal(c.state.members.value.length, 0)
  c.close()
})

const body = text => ({ schemaVersion: 1, type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text, marks: [] }] }] })
const brief = (text, revision = '1') => ({ data: { projectId: '99', body: body(text), revision, allowedActions: ['project:edit'] } })

test('简报账号变化清除正文并中断保存，迟到响应不能回填', async () => {
  let resolve, signal
  const c = setup({ readBrief: async () => brief('原文'), saveBrief: (id, data, key, current) => { signal = current; return new Promise(done => { resolve = done }) } }, 'useProjectWorkspace')
  await c.state.load(); c.state.draft.value = body('修改')
  const pending = c.state.save()
  c.auth.token = 'two'
  assert.equal(signal.aborted, true)
  assert.equal(c.state.brief.value, undefined)
  resolve(brief('修改', '2')); await pending
  assert.equal(c.state.brief.value, undefined)
  assert.equal(c.state.draft.value.content.length, 0)
  assert.equal(c.state.notice.value, '')
  c.close()
})

test('简报保存响应保留发送后的新输入，后续保存使用最新revision', async () => {
  let resolve
  const calls = []
  const c = setup({ readBrief: async () => brief('原文'), saveBrief: (id, data, key) => { calls.push({ data, key }); return new Promise(done => { resolve = done }) } }, 'useProjectWorkspace')
  await c.state.load(); c.state.draft.value = body('第一次')
  const pending = c.state.save(); c.state.draft.value = body('继续编辑')
  resolve(brief('第一次', '2')); await pending
  assert.equal(c.state.dirty.value, true)
  assert.equal(c.state.draft.value.content[0].content[0].text, '继续编辑')
  const next = c.state.save()
  assert.equal(calls[1].data.revision, '2')
  assert.notEqual(calls[1].key, calls[0].key)
  resolve(brief('继续编辑', '3')); await next
  assert.equal(c.state.dirty.value, false)
  c.close()
})

test('简报刷新竞态不覆盖保存，确认重载等待期间新输入保留', async () => {
  const pending = []
  const c = setup({ readBrief: () => new Promise(done => pending.push(done)), saveBrief: async () => brief('保存结果', '2') }, 'useProjectWorkspace')
  const first = c.state.load(); pending.shift()(brief('原文')); await first
  const old = c.state.load()
  c.state.draft.value = body('保存结果'); await c.state.save()
  pending.shift()(brief('旧结果')); await old
  assert.equal(c.state.brief.value.revision, '2')
  const reload = c.state.load(true)
  c.state.draft.value = body('等待期间编辑')
  pending.shift()(brief('服务器新文', '3')); await reload
  assert.equal(c.state.draft.value.content[0].content[0].text, '等待期间编辑')
  assert.equal(c.state.brief.value.revision, '2')
  c.close()
})

test('简报撤权清空已显示内容，缓存停用保留草稿但禁止写入直至重验', async () => {
  let deny = false
  const c = setup({ readBrief: async () => { if (deny) throw new ApiError('无权限', 403); return brief('原文') } }, 'useProjectWorkspace')
  c.hooks.mount(); await tick()
  c.state.draft.value = body('草稿')
  c.hooks.deactivate()
  assert.equal(c.state.canEdit.value, false)
  assert.equal(c.state.dirty.value, true)
  c.hooks.activate(); await tick()
  assert.equal(c.state.canEdit.value, true)
  assert.equal(c.state.draft.value.content[0].content[0].text, '草稿')
  deny = true; await c.state.load()
  assert.equal(c.state.brief.value, undefined)
  assert.equal(c.state.draft.value.content.length, 0)
  assert.ok(c.state.error.value)
  c.close()
})

test('成员筛选取消旧请求并重置页码，旧结果不结束新加载', async () => {
  const pending = []
  const c = setup({ readMembers: (id, page, status, signal) => new Promise(resolve => pending.push({ page, status, signal, resolve })), readRoles: async () => ({ data: { items: [] } }) })
  c.state.page.value = 3
  const first = c.state.load()
  c.state.changeStatus('removed')
  assert.equal(pending[0].signal.aborted, true)
  assert.equal(pending[1].page, 1)
  assert.equal(pending[1].status, 'removed')
  pending[0].resolve({ rows: [{ userId: 'old' }], total: 88 }); await first
  assert.equal(c.state.loading.value, true)
  assert.equal(c.state.total.value, 0)
  pending[1].resolve({ rows: [{ userId: 'removed' }], total: 1 }); await tick()
  assert.equal(c.state.members.value[0].userId, 'removed')
  c.close()
})

test('缓存页面停用清空并停止读取，重新激活重新鉴权且首次挂载不重复', async () => {
  let reads = 0
  const c = setup({ readMembers: async () => { reads++; return { rows: [{ userId: '1' }], total: 1 } }, readRoles: async () => ({ data: { items: [] } }) })
  c.hooks.mount(); c.hooks.activate(); await tick()
  assert.equal(reads, 1)
  c.hooks.deactivate(); await c.state.load()
  assert.equal(reads, 1); assert.equal(c.state.members.value.length, 0)
  c.hooks.activate(); await tick()
  assert.equal(reads, 2); assert.equal(c.state.total.value, 1)
  c.close()
})

test('角色读取被拒绝不保留成员列表或旧分页', async () => {
  const c = setup({ readMembers: async () => ({ rows: [{ userId: '1' }], total: 100 }), readRoles: async () => { throw new Error('无权限') } })
  c.state.total.value = 100
  await c.state.load()
  assert.ok(c.state.error.value)
  assert.equal(c.state.total.value, 0)
  assert.equal(c.state.members.value.length, 0)
  assert.equal(c.state.loading.value, false)
  c.close()
})

test('成员数量减少回退到有效末页，等待重载并保留筛选，只读取一次角色', async () => {
  const pending = []
  let roleReads = 0
  const c = setup({ readMembers: (id, page, status, signal) => new Promise(resolve => pending.push({ page, status, signal, resolve })), readRoles: async () => { roleReads++; return { data: { items: [{ id: 'viewer' }] } } } })
  c.state.page.value = 4; c.state.status.value = 'removed'
  let done = false
  const refresh = c.state.load().then(() => { done = true })
  pending[0].resolve({ rows: [], total: 21 }); await tick()
  assert.equal(c.state.page.value, 2)
  assert.equal(pending[1].page, 2); assert.equal(pending[1].status, 'removed')
  assert.equal(done, false); assert.equal(c.state.loading.value, true)
  assert.equal(c.state.members.value.length, 0)
  pending[1].resolve({ rows: [{ userId: 'remaining' }], total: 21 }); await refresh
  assert.equal(c.state.members.value[0].userId, 'remaining')
  assert.equal(c.state.total.value, 21); assert.equal(c.state.loading.value, false)
  assert.equal(roleReads, 1); assert.equal(pending.length, 2)
  c.state.changePage(2); c.state.changePage(0); c.state.changePage(NaN); c.state.changePage(1.5)
  assert.equal(pending.length, 2)
  c.close()
})

test('成员连续减少逐次回退，全部移除时不追加空列表查询', async () => {
  const pages = []
  const totals = [41, 21, 0]
  const c = setup({ readMembers: async (id, page) => { pages.push(page); return { rows: [], total: totals.shift() } }, readRoles: async () => ({ data: { items: [] } }) })
  c.state.page.value = 5
  await c.state.load()
  assert.deepEqual(pages, [5, 3, 2])
  assert.equal(c.state.page.value, 1); assert.equal(c.state.total.value, 0)
  assert.equal(c.state.members.value.length, 0); assert.equal(c.state.loading.value, false)
  c.close()
})

test('成员回退请求在账号切换或筛选变化后不能回填旧成员与角色', async () => {
  for (const action of ['account', 'filter']) {
    const pending = []
    const c = setup({ readMembers: (id, page, status, signal) => new Promise(resolve => pending.push({ page, status, signal, resolve })), readRoles: async () => ({ data: { items: [{ id: 'old-role' }] } }) })
    c.state.page.value = 3
    const refresh = c.state.load()
    pending[0].resolve({ rows: [], total: 1 }); await tick()
    assert.equal(pending.length, 2)
    if (action === 'account') c.auth.token = 'two'
    else c.state.changeStatus('removed')
    assert.equal(pending[1].signal.aborted, true)
    pending[1].resolve({ rows: [{ userId: 'old-member' }], total: 1 }); await refresh
    assert.equal(c.state.members.value.length, 0); assert.equal(c.state.roles.value.length, 0)
    if (action === 'filter') {
      assert.equal(c.state.loading.value, true)
      pending[2].resolve({ rows: [{ userId: 'removed' }], total: 1 }); await tick()
      assert.equal(c.state.members.value[0].userId, 'removed')
    }
    c.close()
  }
})

test('成员回退读取失败清空列表与角色，重试从修正后的页码开始', async () => {
  const pages = []
  let fail = true
  const c = setup({ readMembers: async (id, page) => {
    pages.push(page)
    if (page === 4) return { rows: [], total: 21 }
    if (fail) throw new ApiError('访问被拒绝', 403)
    return { rows: [{ userId: 'ok' }], total: 21 }
  }, readRoles: async () => ({ data: { items: [{ id: 'role' }] } }) })
  c.state.page.value = 4; await c.state.load()
  assert.equal(c.state.page.value, 2); assert.equal(c.state.loading.value, false)
  assert.equal(c.state.total.value, 0); assert.equal(c.state.roles.value.length, 0)
  assert.equal(c.state.members.value.length, 0); assert.ok(c.state.error.value)
  fail = false; await c.state.load()
  assert.deepEqual(pages, [4, 2, 2]); assert.equal(c.state.members.value[0].userId, 'ok')
  c.close()
})

test('切换项目复用页面仍提示未保存简报，保存中拒绝切换', async () => {
  let resolve, prompts = 0
  const c = setup({ readBrief: async () => brief('原文'), saveBrief: () => new Promise(done => { resolve = done }) },
    'useProjectWorkspace', async () => { prompts++; throw new Error('取消') })
  await c.state.load(); c.state.draft.value = body('未保存')
  const old = { params: { id: '99' } }, next = { params: { id: '100' } }
  assert.equal(await c.hooks.update(next, old), false); assert.equal(prompts, 1)
  assert.equal(c.hooks.update(old, old), true); assert.equal(prompts, 1)
  const saving = c.state.save()
  assert.equal(await c.hooks.update(next, old), false); assert.equal(prompts, 1)
  resolve(brief('未保存', '2')); await saving
  assert.equal(await c.hooks.update(next, old), true); c.close()
})
