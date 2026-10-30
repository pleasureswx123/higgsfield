const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(api) {
 const exports = {}, auth = vue.reactive({ token:'a' })
 const data = { revision:'0',canEdit:true, rows:[{code:'asset:edit',editable:true}], roles:[{code:'owner',permissions:{'asset:edit':'project'},defaults:{'asset:edit':'project'}},{code:'producer',permissions:{},defaults:{}}] }
 runInNewContext(ts.transpileModule(readFileSync('src/composables/useProjectPermissions.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Error,AbortController,crypto:require('node:crypto'),window:{addEventListener(){},removeEventListener(){}},require(id){
 if(id==='vue')return {...vue,onBeforeUnmount(){}}
 if(id==='vue-router')return {onBeforeRouteLeave(){}}
 if(id==='element-plus')return {ElMessageBox:{confirm:async()=>{}}}
 if(id==='@/stores/auth')return {useAuthStore:()=>auth}
 return {readProjectPermissions:async()=>({data}),...api}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useProjectPermissions('2',()=>{}))
 return {state,data,auth,close:()=>scope.stop()}
}
test('恢复默认没有改动时不产生脏状态，调整后恢复默认',async()=>{
 const c=setup();await tick();c.state.reset();assert.equal(c.state.dirty.value,false)
 c.state.draft.value.producer['asset:edit']='own';assert.equal(c.state.dirty.value,true)
 c.state.reset();assert.equal(c.state.draft.value.producer['asset:edit'],'none');assert.equal(c.state.dirty.value,false);c.close()
})
test('保存错误保留草稿和幂等键以便重试',async()=>{
 const calls=[];const c=setup({saveProjectPermissions:async(...args)=>{calls.push(args);throw Error('网络故障')}});await tick()
 c.state.draft.value.producer['asset:edit']='own';await c.state.save();await c.state.save()
 assert.equal(calls.length,2);assert.equal(calls[0][2],calls[1][2]);assert.equal(c.state.dirty.value,true);assert.equal(c.state.error.value,'网络故障');c.close()
})
test('账号切换后的迟到保存不回填旧矩阵',async()=>{
 let resolve;const c=setup({saveProjectPermissions:()=>new Promise(done=>resolve=done)});await tick()
 c.state.draft.value.producer['asset:edit']='own';const pending=c.state.save();c.auth.token='b'
 resolve({data:c.data});await pending;assert.equal(c.state.matrix.value,undefined);c.close()
})
