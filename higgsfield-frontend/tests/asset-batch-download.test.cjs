const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(setImmediate)
function setup() {
  const exports = {}, calls = [], anchors = [], revoked = [], timers = new Map(), hooks = {}
  const auth = vue.reactive({ token: 'one', user: { permissions: ['asset:download'] } }), allowed = vue.ref(true)
  const rows = vue.ref([{ id: '9007199254740993', name: '甲', currentVersionId: '901', file: { mimeType: 'image/png' } }, { id: '2', name: '乙.png', currentVersionId: '902', file: { mimeType: 'image/png' } }])
  const selected = vue.ref(rows.value.map(x => x.id)); let timerId = 0, urlId = 0
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useAssetBatchDownload.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, Error, AbortController, URL: { createObjectURL: () => `blob:${++urlId}`, revokeObjectURL: url => revoked.push(url) },
    setTimeout: fn => { timers.set(++timerId, fn); return timerId }, clearTimeout: id => timers.delete(id),
    document: { createElement: () => { const anchor = { click() { anchors.push({ href: this.href, download: this.download }) } }; return anchor } },
    require(id) {
      if (id === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.close = fn } }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn }, onBeforeRouteUpdate: fn => { hooks.update = fn } }
      if (id.includes('stores/auth')) return { useAuthStore: () => auth }
      if (id.includes('assetFormats')) return { assetExtension: () => '.png' }
      return { readMedia: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useAssetBatchDownload(() => rows.value, selected, () => allowed.value))
  return { state, rows, selected, auth, allowed, calls, anchors, revoked, timers, hooks, close() { hooks.close(); scope.stop() } }
}

test('批量下载顺序读取固定版本，失败保留选择，成功只报告交给浏览器', async () => {
  const h = setup(), run = h.state.download()
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].args[0], '901'); assert.equal(h.calls[0].args[1], true)
  assert.equal(h.hooks.leave(), false)
  h.rows.value[1].currentVersionId = '999'; h.rows.value[1].name = '已改名'
  h.calls[0].args[3](123); assert.equal(h.state.loadedBytes.value, 123)
  h.calls[0].resolve({}); await tick()
  assert.equal(h.anchors[0].download, '甲.png'); assert.equal(h.calls[1].args[0], '902')
  h.calls[1].reject(new Error('没有下载权限')); await run
  assert.equal(h.selected.value.length, 1); assert.equal(h.selected.value[0], '2')
  assert.match(h.state.message.value, /已交给浏览器 1 个文件/); assert.match(h.state.message.value, /乙.png：没有下载权限/)
  assert.equal(h.hooks.leave(), true); assert.equal(h.revoked.length, 0)
  for (const callback of h.timers.values()) callback()
  assert.equal(h.revoked[0], 'blob:1'); h.close()
})

test('停止下载中断当前读取且不启动后续项，保持未完成选择', async () => {
  const h = setup(), run = h.state.download()
  h.state.stop(); assert.equal(h.calls[0].args[2].aborted, true)
  h.calls[0].resolve({}); await run
  assert.equal(h.calls.length, 1); assert.equal(h.anchors.length, 0); assert.equal(h.selected.value.length, 2)
  assert.match(h.state.message.value, /剩余 2 项未完成/); h.close()
})

test('缓存停用和权限变化取消下载，账号切换阻断迟到文件触发', async () => {
  const h = setup(), run = h.state.download()
  h.hooks.deactivate(); h.calls[0].resolve({}); await run
  await h.state.download(); assert.equal(h.calls.length, 1); assert.equal(h.anchors.length, 0)
  h.hooks.activate(); const second = h.state.download()
  h.auth.user.permissions=[]; assert.equal(h.calls[1].args[2].aborted, true)
  h.calls[1].resolve({}); await second; assert.equal(h.anchors.length, 0)
  const third = h.state.download(); h.auth.token = 'two'
  h.calls[2].resolve({}); await third
  assert.equal(h.anchors.length, 0); assert.equal(h.state.message.value, ''); assert.equal(h.state.pending.value, false)
  h.close()
})
