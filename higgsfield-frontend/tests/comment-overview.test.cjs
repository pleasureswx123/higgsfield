const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function setup(pages) {
 const exports={}, requested=[]
 const code=ts.transpileModule(readFileSync('src/composables/useCommentOverview.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
 runInNewContext(code,{exports,AbortController,Date,Error,require(id){
  if(id==='vue') return {...vue,watch(){},onBeforeUnmount(){}}
  if(id==='@/stores/auth') return {useAuthStore:()=>({token:'valid'})}
  return {listCommentThreads:async()=>({total:1,rows:[{id:'1'}]}),listComments:async(id,page)=>{requested.push(page);return {total:pages.flat().length,rows:pages[page-1]||[]}}}
 }})
 return {api:exports.useCommentOverview(()=>({assetVersionId:'7'}),()=>true),requested}
}
test('全部删除后列表为空，供侧栏显示暂无评论',async()=>{
 const {api}=setup([[{id:'1',deleted:true,createTime:'2026-10-30'}]])
 await api.reload();assert.equal(api.rows.value.length,0)
})
test('删除行仍计入分页进度，保留后续页的有效回复',async()=>{
 const {api,requested}=setup([[{id:'1',deleted:true}],[{id:'2',deleted:false,createTime:'2026-10-30'}]])
 await api.reload();assert.deepEqual(requested,[1,2]);assert.equal(api.rows.value.length,1);assert.equal(api.rows.value[0].id,'2')
})
