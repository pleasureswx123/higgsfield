const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const item = (id, generated = true) => ({ asset: { id, uploaded: !generated } })
function setup(refresh, ready = () => true) {
 const output = {}, timers = new Map(); let id = 0, cleanup
 runInNewContext(ts.transpileModule(readFileSync('src/composables/useAssetArrivalHighlights.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
  exports: output, Set, JSON,
  require: () => ({ ...vue, onBeforeUnmount: fn => { cleanup = fn } }),
  setTimeout: fn => { timers.set(++id, fn); return id }, clearTimeout: id => timers.delete(id),
 })
 const rows = vue.ref([item('1')]), context = vue.ref('项目2/目录9'), scope = vue.effectScope()
 const result = scope.run(() => output.useAssetArrivalHighlights(() => rows.value, () => context.value, () => refresh(rows), ready))
 return { ...result, rows, context, timers, close() { cleanup(); scope.stop() } }
}
test('只强调刷新后新增素材，重复刷新不重复高亮，超时与卸载清理', async () => {
 const c = setup(async rows => { rows.value = [item('1'), item('2'), item('3', false)] })
 await c.refreshGenerated(); assert.deepEqual([...c.highlighted.value], ['2', '3'])
 assert.equal(c.timers.size, 1); [...c.timers.values()][0](); assert.equal(c.highlighted.value.length, 0)
 await c.refreshGenerated(); assert.equal(c.highlighted.value.length, 0)
 c.close(); assert.equal(c.timers.size, 0)
})
test('刷新中切目录、卸载或缺失可靠旧列表时，不强调其他上下文的结果', async () => {
 let finish
 const c = setup(rows => new Promise(resolve => { finish = () => { rows.value = [item('2')]; resolve() } }))
 const pending = c.refreshGenerated(); c.context.value = '项目3/目录1'; finish(); await pending
 assert.equal(c.highlighted.value.length, 0)
 const next = c.refreshGenerated(); c.close(); finish(); await next
 assert.equal(c.highlighted.value.length, 0)
 const offline = setup(async rows => { rows.value = [item('8')] }, () => false)
 await offline.refreshGenerated(); assert.equal(offline.highlighted.value.length, 0); offline.close()
})
