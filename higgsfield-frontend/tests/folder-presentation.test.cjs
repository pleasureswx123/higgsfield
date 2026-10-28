const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function harness(load = async () => {}) {
  const exports = {}, auth = vue.reactive({ token: 'one' }), expanded = vue.reactive(new Set())
  let unmount
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useFolderPresentation.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, require: name => name === 'vue' ? { ...vue, onBeforeUnmount: fn => { unmount = fn } } : { useAuthStore: () => auth },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useFolderPresentation(expanded, load))
  return { state, auth, expanded, close() { unmount(); scope.stop() } }
}
test('个人置顶和同级顺序不修改服务端数组，恢复复制数组并保留大整数ID', async () => {
  const h = harness(), rows = [{ id: '9007199254740993' }, { id: '2' }, { id: '3' }]
  h.state.moveUp(rows, '3')
  assert.equal(h.state.arrange(rows).map(x => x.id).join(','), '9007199254740993,3,2')
  assert.equal(rows.map(x => x.id).join(','), '9007199254740993,2,3')
  h.state.pin('2'); assert.equal(h.state.arrange(rows)[0].id, '2')
  h.state.moveUp(rows, '9007199254740993'); assert.match(h.state.notice.value, /置顶/)
  const saved = { pinnedFolderIds: ['3'], folderOrderIds: ['3','2'], expandedFolderIds: ['9007199254740993'] }
  await h.state.restore(saved); h.state.pin('2')
  assert.deepEqual(saved.pinnedFolderIds, ['3']); assert.equal(h.expanded.has('9007199254740993'), true)
  h.auth.token = 'two'; await vue.nextTick()
  assert.equal(h.state.pinned.value.length, 0); assert.equal(h.expanded.size, 0)
  h.close()
})
test('重复恢复取消旧的展开加载序列，置顶上限不会静默丢弃已有设置', async () => {
  const calls = []; const h = harness(id => new Promise(resolve => calls.push({ id, resolve })))
  const old = h.state.restore({ expandedFolderIds: ['1','2'] })
  const current = h.state.restore({ expandedFolderIds: ['3'] })
  calls[0].resolve(); await old; calls[1].resolve(); await current
  assert.equal(calls.map(x => x.id).join(','), '1,3'); assert.equal([...h.expanded].join(','), '3')
  await h.state.restore({ pinnedFolderIds: Array.from({ length: 500 }, (_, i) => String(i + 1)) })
  h.state.pin('501'); assert.equal(h.state.pinned.value.length, 500); assert.match(h.state.notice.value, /500/)
  h.close()
})
