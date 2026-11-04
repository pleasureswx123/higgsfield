const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(kind, count = 2, fault = '') {
  const auth = vue.reactive({ token: 'one' }), visible = vue.ref(true), hooks = [], calls = [], restored = new Set(), keys = new Map()
  let refreshes = 0, listFault = false, failed = false, releaseRefresh
  const fixtures = Array.from({ length: count }, (_, i) => ({ id: String(i + 1), targetId: String(i + 101), revision: '2', kind, name: '验证' + i, deletedTime: String(count - i).padStart(3, '0'), canRestore: true }))
  const cache = {}
  class ApiError extends Error {}
  function load(name) {
    if (cache[name]) return cache[name]
    const exports = {}; cache[name] = exports
    runInNewContext(ts.transpileModule(readFileSync(join(__dirname, `../src/composables/${name}.ts`), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
      exports, AbortController, Map, Error, crypto: require('node:crypto').webcrypto, require(id) {
        if (id === 'vue') return { ...vue, onBeforeUnmount: fn => hooks.push(fn), onActivated() {}, onDeactivated() {} }
        if (id === 'vue-router') return { onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} }
        if (id === '@/stores/auth') return { useAuthStore: () => auth }
        if (id === '@/api/client') return { ApiError }
        if (id === 'element-plus') return { ElMessageBox: { confirm: async () => {} } }
        if (id.startsWith('./')) return load(id.slice(2))
        if (id === '@/api/projectTrash') return {
          listProjectTrash: async (_project, _kind, page) => {
            if (listFault) throw new Error('读取断网')
            const rows = fixtures.filter(row => !restored.has(row.id))
            return { rows: rows.slice((page - 1) * 30, page * 30), total: rows.length, hasNext: page * 30 < rows.length }
          },
          restoreProjectTrash: async (item, key) => {
            calls.push({ id: item.id, revision: item.revision, key })
            if (keys.has(key)) return keys.get(key)
            if (fault === 'before' && !failed && item.id === String(count)) { failed = true; throw new Error('请求超时') }
            assert.ok(!restored.has(item.id), '已经成功的条目不能使用新键重复恢复')
            restored.add(item.id); keys.set(key, item)
            if (fault === 'after' && !failed) { failed = true; throw new Error('响应丢失') }
            return item
          },
        }
        throw new Error(id)
      },
    })
    return exports
  }
  const scope = vue.effectScope(), state = scope.run(() => load('useProjectTrash').useProjectTrash('2', () => [kind === 'folder' ? 'folder:write' : `${kind}:remove`], () => visible.value, async () => {
    if (fault === 'slow-refresh') await new Promise(resolve => { releaseRefresh = resolve })
    refreshes++
  }))
  return { state, calls, restored, keys, fixtures, visible, auth, refreshes: () => refreshes, failList(value) { listFault = value }, release() { releaseRefresh() }, close() { hooks.forEach(fn => fn()); scope.stop() } }
}
for (const kind of ['asset', 'element', 'folder']) {
  test(`${kind} 单项与批量恢复同步移出列表和更新总数`, async () => {
    const h = setup(kind, 3); await tick()
    await h.state.restore(h.state.rows.value[0])
    assert.equal(h.state.total.value, 2); assert.equal(h.state.rows.value.length, 2); assert.equal(h.refreshes(), 1)
    h.state.batch.selectAll(true); await h.state.batch.restore()
    assert.equal(h.state.total.value, 0); assert.equal(h.state.rows.value.length, 0); assert.equal(h.restored.size, 3); assert.equal(h.refreshes(), 2)
    h.close()
  })
  test(`${kind} 服务端成功但响应丢失，原请求重试不重复恢复`, async () => {
    const h = setup(kind, 1, 'after'); await tick()
    await h.state.restore(h.state.rows.value[0])
    assert.equal(h.state.rows.value.length, 0); assert.equal(h.state.batch.uncertainCount.value, 1)
    await h.state.batch.retryUncertain()
    assert.equal(h.calls.length, 2); assert.equal(h.calls[0].key, h.calls[1].key); assert.equal(h.keys.size, 1)
    assert.equal(h.state.batch.uncertainCount.value, 0); assert.equal(h.refreshes(), 2)
    h.close()
  })
}
test('后续页单项失败后保留列表和原键重试入口', async () => {
  const h = setup('asset', 61, 'before'); await tick(); await h.state.load(true); await h.state.load(true)
  const item = h.state.rows.value.find(row => row.id === '61')
  await h.state.restore(item)
  assert.equal(h.state.rows.value.length, 61); assert.equal(h.state.batch.selected.value[0], '61')
  await h.state.batch.restore()
  assert.equal(h.state.total.value, 60); assert.equal(h.calls[0].key, h.calls[1].key); assert.equal(h.restored.size, 1)
  h.close()
})
test('读取刷新失败保留原列表，恢复后的侧栏刷新完成前保持提交锁', async () => {
  const h = setup('folder', 2, 'slow-refresh'); await tick()
  h.failList(true); await h.state.load(); assert.equal(h.state.rows.value.length, 2); assert.ok(h.state.errors.folder)
  h.failList(false)
  const pending = h.state.restore(h.state.rows.value[0]); await tick()
  assert.equal(h.state.batch.pending.value, true); assert.equal(h.refreshes(), 0)
  h.release(); await pending
  assert.equal(h.state.batch.pending.value, false); assert.equal(h.refreshes(), 1)
  h.close()
})
