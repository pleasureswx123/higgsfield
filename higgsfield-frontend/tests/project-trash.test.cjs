const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(list) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one' })
  const actions = vue.ref(['asset:remove', 'element:remove', 'folder:write']), visible = vue.ref(true)
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProjectTrash.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, AbortController, Map, Error, require(id) {
      if (id === 'vue') return { ...vue, onBeforeUnmount: fn => { hooks.close = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/api/projectTrash') return { listProjectTrash: list }
      if (id === './useBatchRestore') return { useBatchRestore: () => ({ selected: vue.ref([]), pending: vue.ref(false), restore() {} }) }
      throw new Error(id)
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useProjectTrash('2', () => actions.value, () => visible.value, () => {}))
  return { state, auth, actions, visible, close() { hooks.close(); scope.stop() } }
}
const row = (kind, id = kind) => ({ id, kind, name: id, targetId: id, revision: '1', deletedTime: '2026-11-04', canRestore: true })
test('分类合并保留部分失败，切换分类不会重新请求或混入其他类型', async () => {
  let calls = 0
  const c = setup(async (_id, kind) => { calls++; if (kind === 'element') throw new Error('禁止访问'); return { rows: [row(kind)], total: 1 } })
  await tick()
  assert.equal(c.state.rows.value.length, 2)
  assert.equal(c.state.errors.element, '禁止访问')
  c.state.category.value = 'asset'
  assert.equal(c.state.rows.value.length, 1)
  assert.equal(c.state.rows.value[0].kind, 'asset')
  assert.equal(calls, 3)
  c.close()
})
test('追加分页去重，恢复权限减少后不暴露旧分类内容', async () => {
  const c = setup(async (_id, kind, page) => ({ rows: page === 1 ? [row(kind)] : [row(kind), row(kind, kind + '2')], total: 2 }))
  await tick(); await c.state.load(true)
  assert.equal(c.state.rows.value.length, 6)
  c.actions.value = ['asset:remove']; await tick()
  assert.equal(c.state.rows.value.length, 1)
  assert.equal(c.state.rows.value[0].kind, 'asset')
  c.close()
})
test('退出账号中断请求，迟到响应不得重新显示回收内容', async () => {
  const pending = []
  const c = setup((_id, kind, _page, signal) => new Promise(resolve => pending.push({ kind, signal, resolve })))
  c.auth.token = ''; await tick()
  assert.ok(pending.every(item => item.signal.aborted))
  for (const item of pending) item.resolve({ rows: [row(item.kind)], total: 1 })
  await tick(); assert.equal(c.state.rows.value.length, 0)
  c.close()
})




test('统一恢复按类型调用原接口，并原样保留目标ID、修订和幂等键', async () => {
  const exports = {}, calls = []
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/api/projectTrash.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, require(id) {
      if (id === './client') return {}
      if (id === './assets') return { recycleAsset: (...args) => calls.push(['asset', ...args]) }
      if (id === './elements') return { recycleElement: (...args) => calls.push(['element', ...args]) }
      if (id === './folders') return { actOnFolder: (...args) => calls.push(['folder', ...args]) }
      throw new Error(id)
    },
  })
  for (const kind of ['asset', 'element', 'folder']) await exports.restoreProjectTrash({ ...row(kind), targetId: '9007199254740993', revision: '7' }, 'same-key')
  assert.deepEqual(calls.slice(0, 2), [['asset', '9007199254740993', '7', true, 'same-key'], ['element', '9007199254740993', '7', true, 'same-key']])
  assert.equal(JSON.stringify(calls[2]), JSON.stringify(['folder', '9007199254740993', 'restore', { revision: '7' }, 'same-key']))
})
