const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
test('元素读取取消与账号切换隔离，确认后的恢复不跨账号提交',async()=>{
 const exports={},auth=vue.reactive({token:'one',user:{permissions:[]}}),reads=[],writes=[];let confirm,close,activate,deactivate,confirmCount=0
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useElements.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{
  exports,AbortController,crypto:{randomUUID:()=> 'key'},require(id){
   if(id==='vue')return {...vue,onBeforeUnmount:fn=>{close=fn},onActivated:fn=>{activate=fn},onDeactivated:fn=>{deactivate=fn}}
   if(id==='element-plus')return {ElMessageBox:{confirm:()=>new Promise(resolve=>{confirmCount++;confirm=resolve})}}
   if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
   return {listElements:(...args)=>new Promise(resolve=>reads.push({args,resolve})),recycleElement:async(...args)=>writes.push(args)}
  }
 })
 const scope=vue.effectScope(),state=scope.run(()=>exports.useElements('99'))
  activate();assert.equal(reads.length,1)
 state.search.value='保留筛选';deactivate();assert.equal(reads[0].args[2].aborted,true)
 await state.refresh();assert.equal(reads.length,1)
 activate();assert.equal(reads.length,2);assert.equal(reads[1].args[1].q,'保留筛选')
 reads[1].resolve({rows:[{id:'fresh'}],total:1});await new Promise(setImmediate)
 assert.equal(state.rows.value[0].id,'fresh')
 auth.user.permissions.push('element:read');assert.equal(reads.length,3);assert.equal(state.rows.value.length,0)
 state.open('1');const restoring=state.restore({id:'1',targetId:'9',revision:'2',name:'角色',canRestore:true})
 auth.token='';confirm();await restoring
 assert.equal(reads[0].args[2].aborted,true);assert.equal(writes.length,0);assert.equal(state.editorOpen.value,false)
 reads[0].resolve({rows:[{id:'old'}],total:1});await new Promise(setImmediate)
 assert.equal(state.rows.value.length,0);assert.equal(state.total.value,0)
 await state.refresh();assert.equal(reads.length,3)
 auth.token='two'
 const item={id:'1',targetId:'9',revision:'2',name:'角色',canRestore:true}
 const stale=state.restore(item)
 assert.equal(state.pending.value,true)
 await state.restore(item);assert.equal(confirmCount,2)
 deactivate();activate();confirm();await stale
 assert.equal(writes.length,0);assert.equal(state.pending.value,false)
 close();scope.stop()
})

