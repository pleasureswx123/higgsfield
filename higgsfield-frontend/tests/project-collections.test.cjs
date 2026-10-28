const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code = code; this.errorCode = errorCode } }
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(api = {}, confirm = async () => {}) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one', user: { permissions: [] } }), changes = []
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjectCollections.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, Error, AbortController, crypto: { randomUUID }, require(id) {
      if (id === 'vue') return { ...vue, onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn } }
      if (id === 'element-plus') return { ElMessageBox: { confirm } }
      if (id === '@/api/client') return { ApiError }
      return { getProjectCollections: async () => ({ rows: [], hasNext: false }), ...api }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useProjectCollections(id => changes.push(id)))
  state.form.value = { validate: async () => true }
  return { state, hooks, auth, changes, close: () => { hooks.unmount(); scope.stop() } }
}
test('集合分页读取与创建请求契约，未知结果原键重试', async () => {
  const calls = [], pages = []
  const c = setup({ getProjectCollections: async page => { pages.push(page); return { rows: [{ id: String(page) }], hasNext: page === 1 } }, createProjectCollection: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('网络断开') } })
  await c.state.load(); assert.equal(c.state.rows.value.length, 2)
  c.state.open.value = true; c.state.edit(); c.state.fields.name = '  我的收藏  '
  await c.state.submit(); assert.equal(c.hooks.leave(), false); c.state.close(); assert.equal(c.state.open.value, true)
  c.state.fields.name = '其他内容'; c.hooks.deactivate(); c.hooks.activate(); await c.state.retry()
  assert.equal(calls[0][1], calls[1][1]); assert.equal(calls[1][0].name, '我的收藏')
  assert.deepEqual(Object.keys(calls[1][0]).sort(), ['name', 'orderNum'])
  assert.equal(c.changes.length, 1); c.close()
})
test('删除确认期间账号切换不写入，成功删除报告准确ID', async () => {
  let resolve, writes = 0
  const c = setup({ deleteProjectCollection: async () => { writes++ } }, () => new Promise(done => { resolve = done }))
  const pending = c.state.remove({ id: '99', name: '集合', revision: '3' })
  c.auth.token = 'two'; resolve(); await pending; assert.equal(writes, 0); c.close()
  const d = setup({ deleteProjectCollection: async (id, revision) => { assert.equal(id, '9007199254740993'); assert.equal(revision, '3') } })
  await d.state.remove({ id: '9007199254740993', name: '集合', revision: '3' })
  assert.equal(d.changes[0], '9007199254740993'); d.close()
})
test('编辑清空可选字段并使用当前修订，冲突保留输入并阻止直接覆盖', async () => {
  const c = setup({ updateProjectCollection: async (id, data) => {
    assert.equal(data.revision, '4'); assert.equal(data.description, null); assert.equal(data.color, null)
    throw new ApiError('修订冲突', 601, 'REVISION_CONFLICT')
  } })
  c.state.edit({ id: '5', revision: '4', name: '集合', description: null, color: null, orderNum: 0 })
  await c.state.submit(); assert.equal(c.state.uncertain.value, false); assert.equal(c.state.editing.value, true)
  assert.equal(c.state.conflict.value, true); assert.equal(c.state.fields.name, '集合')
  assert.equal(c.state.error.value, '修订冲突'); c.close()
})

test('手动刷新恢复集合列表后清除上次读取错误', async () => {
  let count = 0
  const c = setup({ getProjectCollections: async () => {
    if (++count === 1) throw new Error('读取失败')
    return { rows: [{ id: '7' }], hasNext: false }
  } })
  await c.state.load(); assert.equal(c.state.readError.value, '读取失败')
  c.state.reload(); await tick()
  assert.equal(c.state.readError.value, ''); assert.equal(c.state.rows.value[0].id, '7'); c.close()
})

test('冲突后的显式重载期间切换账号，不把旧数据写回新会话', async () => {
  let resolve
  const c = setup({ updateProjectCollection: async () => { throw new ApiError('旧冲突', 601, 'REVISION_CONFLICT') },
    getProjectCollections: () => new Promise(done => { resolve = done }),
  })
  c.state.edit({ id: '5', revision: '4', name: '集合', orderNum: 0 })
  await c.state.submit()
  const pending = c.state.reloadEditor(); await tick()
  const oldResolve = resolve; c.auth.token = ''
  oldResolve({ rows: [{ id: 'old' }], hasNext: false }); await pending
  assert.equal(c.state.error.value, ''); assert.equal(c.state.rows.value.length, 0); c.close()
})

test('冲突后重新载入需确认放弃输入，成功后使用最新修订', async () => {
  let accept = false, writes = 0
  const c = setup({
    updateProjectCollection: async () => { writes++; throw new ApiError('冲突', 601, 'REVISION_CONFLICT') },
    getProjectCollections: async () => ({ rows: [{ id: '5', revision: '6', name: '服务端名称', orderNum: 3 }], hasNext: false }),
  }, async () => { if (!accept) throw new Error('取消') })
  c.state.edit({ id: '5', revision: '4', name: '旧名称', orderNum: 0 })
  c.state.fields.name = '保留输入'; await c.state.submit(); await c.state.submit()
  assert.equal(writes, 1)
  await c.state.reloadEditor(); assert.equal(c.state.fields.name, '保留输入')
  accept = true; await c.state.reloadEditor()
  assert.equal(c.state.fields.name, '服务端名称'); assert.equal(c.state.target.value.revision, '6')
  assert.equal(c.state.conflict.value, false); c.close()
})

test('集合未保存修改取消后保留，返回列表与关闭均需确认', async () => {
  let accept = false
  const c = setup({}, async () => { if (!accept) throw new Error('取消') })
  c.state.open.value = true; c.state.edit(); c.state.fields.name = '未保存集合'
  assert.equal(await c.hooks.leave(), false)
  await c.state.back(); assert.equal(c.state.editing.value, true)
  await c.state.close(); assert.equal(c.state.open.value, true)
  assert.equal(c.state.fields.name, '未保存集合')
  accept = true; await c.state.back()
  assert.equal(c.state.editing.value, false); assert.equal(c.state.open.value, true)
  c.state.close(); assert.equal(c.state.open.value, false); c.close()
})

test('表单校验等待中关闭阻止迟到写入', async () => {
  let resolve, writes = 0
  const c = setup({ createProjectCollection: async () => { writes++ } })
  c.state.open.value = true; c.state.edit()
  c.state.form.value = { validate: () => new Promise(done => { resolve = done }) }
  const pending = c.state.submit(); c.state.close(); resolve(true); await pending
  assert.equal(writes, 0); assert.equal(c.state.open.value, false); c.close()
})
