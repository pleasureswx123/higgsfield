const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = async () => { await vue.nextTick(); await new Promise(resolve => setImmediate(resolve)) }
test('素材缓存停用取消列表，激活和权限变化重新读取，退出后迟到响应不显示', async () => {
  const exports = {}, calls = [], hooks = {}, auth = vue.reactive({ token: 'one', user: { permissions: ['asset:read'] } })
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useAssetLibrary.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, AbortController, URL: { revokeObjectURL() {} }, require(name) {
      if (name === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (name.includes('stores/auth')) return { useAuthStore: () => auth }
      if (name.includes('libraryWindow')) return { libraryWindow: () => ({}) }
      return { listAssets: (...args) => new Promise(resolve => calls.push({ args, resolve })) }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useAssetLibrary('99', vue.ref(null)))
  hooks.activate(); assert.equal(calls.length, 1)
  assert.equal(calls[0].args[1].includeDescendants, false)
  state.includeDescendants.value = true
  hooks.deactivate(); assert.equal(calls[0].args[2].aborted, true)
  calls[0].resolve({ rows: [{ id: 'old' }], total: 1 }); await tick()
  assert.equal(state.rows.value.length, 0); assert.equal(state.total.value, 0)
  hooks.activate(); assert.equal(calls.length, 2)
  assert.equal(calls[1].args[1].includeDescendants, true)
  calls[1].resolve({ rows: [{ id: 'current' }], total: 1 }); await tick()
  assert.equal(state.rows.value.length, 1)
  auth.user.permissions = []; assert.equal(state.rows.value.length, 0); assert.equal(calls.length, 3)
  auth.token = ''; assert.equal(calls[2].args[2].aborted, true)
  calls[2].resolve({ rows: [{ id: 'late' }], total: 1 }); await tick()
  assert.equal(state.rows.value.length, 0); assert.equal(calls.length, 3)
  await state.openMedia({ currentVersionId: '2' }); assert.equal(state.selected.value, null)
  hooks.unmount(); scope.stop()
})

 test('素材清除单项保留其他条件，清除全部回第一页且不重复查询', async () => {
  const exports = {}, calls = [], auth = { token: 'one', user: { permissions: [] } }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useAssetLibrary.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, AbortController, URL: { revokeObjectURL() {} }, require(name) {
      if (name === 'vue') return { ...vue, onActivated() {}, onDeactivated() {}, onBeforeUnmount() {} }
      if (name.includes('stores/auth')) return { useAuthStore: () => auth }
      if (name.includes('libraryWindow')) return { libraryWindow: dates => dates ? { from: dates[0], to: dates[1] } : {} }
      return { listAssets: async (...args) => { calls.push(args); return { rows: [], total: 0 } } }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useAssetLibrary('99', vue.ref('9007199254740993')))
  await tick();state.search.value = '角色';state.fileType.value = 'image';state.activity.value = 'liked'
  state.dates.value = ['2024-02-29','2024-03-01'];state.includeDescendants.value = true
  state.clearFilter('fileType');await tick()
  assert.equal(calls.at(-1)[1].fileType, undefined);assert.equal(calls.at(-1)[1].q, '角色')
  assert.equal(calls.at(-1)[1].activity, 'liked');assert.equal(calls.at(-1)[1].includeDescendants, true)
  state.page.value = 3;await tick();const before = calls.length
  state.clearFilter();await tick()
  assert.equal(calls.length, before + 1);assert.equal(state.page.value, 1)
  const query = calls.at(-1)[1]
  assert.equal(query.q, '');assert.equal(query.activity, undefined);assert.equal(query.includeDescendants, false)
  assert.equal(query.from, undefined);assert.equal(query.to, undefined);assert.equal(query.folderId, '9007199254740993')
  scope.stop()
})

test('素材删除末页后等待回退结果，保留目录与筛选且不重复读取', async () => {
  const exports = {}, calls = [], auth = vue.reactive({ token: 'one', user: { permissions: [] } })
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useAssetLibrary.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, AbortController, URL: { revokeObjectURL() {} }, require(name) {
      if (name === 'vue') return { ...vue, onActivated() {}, onDeactivated() {}, onBeforeUnmount() {} }
      if (name.includes('stores/auth')) return { useAuthStore: () => auth }
      if (name.includes('libraryWindow')) return { libraryWindow: dates => dates ? { from: dates[0], to: dates[1] } : {} }
      return { listAssets: (...args) => new Promise(resolve => calls.push({ args, resolve })) }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useAssetLibrary('99', vue.ref('9007199254740993')))
  calls[0].resolve({ rows: [], total: 31 }); await tick()
  state.search.value='图片';state.fileType.value='image';state.includeDescendants.value=true
  state.dates.value=['2024-02-29','2024-03-01'];state.activity.value='liked'
  state.page.value=2;calls[1].resolve({ rows: [{id:'last'}], total:31 });await tick()
  let done=false;const refresh=state.refresh().then(()=>{done=true})
  calls[2].resolve({rows:[],total:30});await tick()
  assert.equal(calls.length,4);assert.equal(state.page.value,1);assert.equal(done,false)
  const query=calls[3].args[1]
  assert.equal(query.folderId,'9007199254740993');assert.equal(query.includeDescendants,true)
  assert.equal(query.q,'图片');assert.equal(query.fileType,'image');assert.equal(query.activity,'liked')
  assert.equal(query.from,'2024-02-29');assert.equal(query.to,'2024-03-01')
  calls[3].resolve({rows:[{id:'remaining'}],total:30});await refresh
  assert.equal(state.rows.value[0].id,'remaining');assert.equal(state.loading.value,false)
  state.page.value=2;calls[4].resolve({rows:[],total:0});await tick()
  assert.equal(state.page.value,1);assert.equal(state.rows.value.length,0);assert.equal(calls.length,5)
  scope.stop()
})

test('素材v-show显隐停止列表和预览请求，返回保留筛选并重新授权预览', async () => {
 const exports={},calls=[],media=[],hooks={},visible=vue.ref(false),auth=vue.reactive({token:'one',user:{permissions:['asset:read']}})
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useAssetLibrary.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
  exports,AbortController,URL:{revokeObjectURL(){},createObjectURL:()=> 'blob:preview'},require(name){
   if(name==='vue')return {...vue,onActivated:fn=>{hooks.activate=fn},onDeactivated:fn=>{hooks.deactivate=fn},onBeforeUnmount:fn=>{hooks.unmount=fn}}
   if(name.includes('stores/auth'))return {useAuthStore:()=>auth}
   if(name.includes('libraryWindow'))return {libraryWindow:()=>({})}
   return {listAssets:(...args)=>new Promise(resolve=>calls.push({args,resolve})),readMedia:(...args)=>new Promise(resolve=>media.push({args,resolve}))}
  }
 })
 const scope=vue.effectScope(),state=scope.run(()=>exports.useAssetLibrary('99',vue.ref(null),()=>visible.value))
 hooks.activate(); assert.equal(calls.length,0)
 visible.value=true; assert.equal(calls.length,1)
 calls[0].resolve({rows:[{id:'retained'}],total:60}); await tick()
 state.search.value='镜头'; state.page.value=2; assert.equal(calls.length,2)
 const opening=state.openMedia({id:'asset',currentVersionId:'v1',mediaType:'image',name:'图片',file:{mimeType:'image/png'}})
 visible.value=false; assert.equal(calls[1].args[2].aborted,true); assert.equal(media[0].args[2].aborted,true)
 media[0].resolve({}); await opening
 assert.equal(state.selected.value.id,'asset'); assert.equal(state.rows.value[0].id,'retained'); assert.equal(state.mediaUrl.value,'')
 await state.refresh(); assert.equal(calls.length,2)
 visible.value=true; assert.equal(calls.length,3); assert.equal(calls[2].args[1].q,'镜头'); assert.equal(calls[2].args[1].pageNum,2)
 assert.equal(media.length,2); media[1].resolve({}); await tick(); assert.equal(state.mediaUrl.value,'blob:preview')
 auth.token=''; assert.equal(state.selected.value,null); assert.equal(state.mediaUrl.value,'')
 hooks.unmount();scope.stop()
})

