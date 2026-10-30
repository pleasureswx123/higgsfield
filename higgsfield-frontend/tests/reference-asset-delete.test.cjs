const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
function setup(){
 const exports={},calls=[],deletes=[],hooks={},visible=vue.ref(true)
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useReferenceAssetDelete.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Error,AbortController,require(id){
  if(id==='vue')return {...vue,onBeforeUnmount:fn=>hooks.close=fn}
  if(id.includes('useAssetActions'))return {useAssetActions:()=>({actionsLocked:vue.ref(false),lifecycle:async(...args)=>deletes.push(args)})}
  return {readAsset:(...args)=>new Promise(resolve=>calls.push({args,resolve}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useReferenceAssetDelete('1',()=>visible.value,()=>visible.value,()=>{}))
 return {state,calls,deletes,visible,close(){hooks.close();scope.stop()}}
}
const row={kind:'asset',id:'2'}
test('候选删除重新读取权限和当前修订，不信任旧候选',async()=>{
 const h=setup(),pending=h.state.remove(row)
 h.calls[0].resolve({data:{id:'2',revision:'9',allowedActions:['asset:remove']}});await pending
 assert.equal(h.deletes[0][0].revision,'9');assert.equal(h.deletes[0][1],false);h.close()
})
test('无删除权限或关闭面板后的迟到读取不能删除',async()=>{
 for(const closed of [false,true]){
  const h=setup(),pending=h.state.remove(row)
  if(closed){h.visible.value=false;await vue.nextTick()}
  h.calls[0].resolve({data:{id:'2',revision:'9',allowedActions:closed?['asset:remove']:[]}});await pending
  assert.equal(h.deletes.length,0);if(!closed)assert.match(h.state.error.value,/没有删除权限/);h.close()
 }
})
