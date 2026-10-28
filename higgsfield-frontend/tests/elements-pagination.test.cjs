const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(setImmediate)
function setup(initiallyVisible = true) {
  const visible = vue.ref(initiallyVisible)
  const exports = {}, reads = [], auth = vue.reactive({ token: 'one', user: { permissions: [] } })
  let close
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useElements.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, require(id) {
      if (id === 'vue') return { ...vue, onBeforeUnmount: fn => { close = fn }, onActivated() {}, onDeactivated() {} }
      if (id.includes('stores/auth')) return { useAuthStore: () => auth }
      if (id === 'element-plus') return { ElMessageBox: {} }
      return {
        listElements: (project, params, signal) => new Promise(resolve => reads.push({ kind: 'elements', project, params, signal, resolve })),
        listElementTrash: (project, pageNum, signal) => new Promise(resolve => reads.push({ kind: 'trash', project, params: { pageNum }, signal, resolve })),
      }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useElements('9007199254740993', () => visible.value))
  return { state, reads, auth, visible, close() { close(); scope.stop() } }
}

test('元素末页删除后回退有效页，刷新等待回退结果且不重复查询、不丢筛选', async () => {
  const h = setup()
  h.reads[0].resolve({ rows: [{ id: 'first' }], total: 31 }); await tick()
  h.state.search.value = '角色'; h.state.category.value = 'character'; h.state.workStatus.value = 'working'; h.state.group.value = 'drafts'
  h.state.page.value = 2
  h.reads[1].resolve({ rows: [{ id: 'last' }], total: 31 }); await tick()
  let done = false
  const refresh = h.state.refresh().then(() => { done = true })
  h.reads[2].resolve({ rows: [], total: 30 }); await tick()
  assert.equal(h.state.page.value, 1); assert.equal(h.reads.length, 4); assert.equal(done, false)
  assert.equal(h.state.loading.value, true); assert.equal(h.state.rows.value.length, 0)
  assert.equal(h.reads[3].params.pageNum, 1); assert.equal(h.reads[3].params.q, '角色')
  assert.equal(h.reads[3].params.category, 'character'); assert.equal(h.reads[3].params.workStatus, 'working')
  assert.equal(h.reads[3].params.statusGroup, 'drafts'); assert.equal(h.reads[3].project, '9007199254740993')
  h.reads[3].resolve({ rows: [{ id: 'remaining' }], total: 30 }); await refresh
  assert.equal(h.state.rows.value[0].id, 'remaining'); assert.equal(h.state.total.value, 30)
  assert.equal(h.state.loading.value, false); assert.equal(h.reads.length, 4); h.close()
})

test('回收站恢复末页后同样回退，无记录时直接回第一页且不重复查询', async () => {
  const h = setup()
  h.reads[0].resolve({ rows: [], total: 0 }); await tick()
  h.state.trash.value = true; await tick()
  h.reads[1].resolve({ rows: [{ id: 'trash-first' }], total: 61 }); await tick()
  h.state.page.value = 3
  h.reads[2].resolve({ rows: [], total: 30 }); await tick()
  assert.equal(h.state.page.value, 1); assert.equal(h.reads.length, 4)
  assert.equal(h.reads[3].kind, 'trash')
  h.reads[3].resolve({ rows: [{ id: 'recycled' }], total: 30 }); await tick()
  assert.equal(h.state.recycled.value[0].id, 'recycled')
  h.state.page.value = 2
  h.reads[4].resolve({ rows: [], total: 0 }); await tick()
  assert.equal(h.state.page.value, 1); assert.equal(h.state.total.value, 0)
  assert.equal(h.state.recycled.value.length, 0); assert.equal(h.state.loading.value, false)
  assert.equal(h.reads.length, 5); h.close()
})

test('页码修正期间账号变化取消旧读取，不回填旧账号列表', async () => {
  const h = setup()
  h.reads[0].resolve({ rows: [], total: 61 }); await tick()
  h.state.page.value = 3
  h.reads[1].resolve({ rows: [], total: 30 }); await tick()
  assert.equal(h.reads.length, 3)
  h.auth.token = 'two'; assert.equal(h.reads[2].signal.aborted, true)
  h.reads[3].resolve({ rows: [{ id: 'new' }], total: 1 }); await tick()
  h.reads[2].resolve({ rows: [{ id: 'old' }], total: 30 }); await tick()
  assert.equal(h.state.rows.value[0].id, 'new'); assert.equal(h.state.total.value, 1)
  assert.equal(h.state.page.value, 1); h.close()
})

test('元素页签首次隐藏不加载，往返保留列表筛选并拒绝迟到响应',async()=>{
 const h=setup(false)
 assert.equal(h.reads.length,0);h.visible.value=true;assert.equal(h.reads.length,1)
 h.reads[0].resolve({rows:[{id:'selected'}],total:31});await tick()
 h.state.search.value='保留搜索';h.state.category.value='character';h.state.page.value=2
 assert.equal(h.reads.length,2)
 h.visible.value=false;assert.equal(h.reads[1].signal.aborted,true)
 assert.equal(h.state.rows.value[0].id,'selected');assert.equal(h.state.loading.value,false)
 h.reads[1].resolve({rows:[{id:'stale'}],total:31});await tick()
 assert.equal(h.state.rows.value[0].id,'selected')
 await h.state.refresh();h.state.open('hidden');assert.equal(h.reads.length,2);assert.equal(h.state.editorOpen.value,false)
 h.visible.value=true;assert.equal(h.reads.length,3)
 assert.equal(h.reads[2].params.pageNum,2);assert.equal(h.reads[2].params.q,'保留搜索');assert.equal(h.reads[2].params.category,'character')
 h.visible.value=false;h.auth.token='';assert.equal(h.state.rows.value.length,0)
 h.close()
})
