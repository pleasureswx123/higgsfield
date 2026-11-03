const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

test('目录查询包含视频，归档完成自动通知素材刷新', async () => {
  const exports = {}, calls = [], hooks = {}
  let ready = 0, refreshed = 0
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useCreationProgress.ts'), 'utf8')
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, Error, setTimeout: () => 1, clearTimeout: () => {},
    require: name => name === 'vue' ? { ...vue, onActivated: () => {}, onDeactivated: () => {}, onBeforeUnmount: fn => { hooks.close = fn } }
      : name === '@/stores/auth' ? { useAuthStore: () => ({ token: 'token' }) }
      : { listGenerations: async query => { calls.push(query); return { rows: [{ id: '7', kind: 'video', orchestrationState: 'finished', archiveSummary: { ready, failed: 0 } }] } } },
  })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useCreationProgress(() => '2', () => '5', () => undefined, () => { refreshed++ }))
  await Promise.resolve()
  assert.equal(calls[0].kind, undefined)
  assert.equal(calls[0].folderId, '5')
  const before = refreshed
  ready = 1
  await state.reload()
  assert.equal(refreshed, before + 1)
  assert.equal(state.label(state.rows.value[0]), '已保存 1 个视频')
  await state.reload()
  assert.equal(refreshed, before + 1)
  hooks.close()
  scope.stop()
})
