const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
const tick=()=>new Promise(setImmediate)
function setup(){
 const exports={},hooks={},reads=[],media=[],revoked=[],visible=vue.ref(false),auth=vue.reactive({token:'one',user:{user:{userId:'1'},permissions:['element:read']}})
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useElementHistory.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{
 exports,AbortController,URL:{createObjectURL:()=> 'blob:history',revokeObjectURL:url=>revoked.push(url)},require(id){
 if(id==='vue')return {...vue,onBeforeUnmount:fn=>hooks.close=fn,onActivated:fn=>hooks.activate=fn,onDeactivated:fn=>hooks.deactivate=fn}
 if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
 return {listRevisions:(...args)=>new Promise(resolve=>reads.push({args,resolve})),readMedia:(...args)=>new Promise(resolve=>media.push({args,resolve}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useElementHistory('9',()=>visible.value))
 return {state,visible,auth,reads,media,revoked,hooks,close(){hooks.close();scope.stop()}}
}
const revisions=[{id:'r1',media:[{assetVersionId:'v1',isPrimary:true}],propertySnapshot:[]},{id:'r2',media:[{assetVersionId:'v2',isPrimary:true},{assetVersionId:'v3'}],propertySnapshot:[]}]
test('历史弹窗隐藏取消媒体，返回保持修订和所选图片并重新授权读取',async()=>{
 const h=setup();assert.equal(h.reads.length,0);h.visible.value=true
 h.reads[0].resolve({rows:revisions,total:2});await tick();h.state.choose(revisions[1]);await tick()
 h.state.selectedVersion.value='v3';await tick();const last=h.media.at(-1)
 h.visible.value=false;assert.equal(last.args[2].aborted,true)
 last.resolve({});await tick();assert.equal(h.state.preview.value,'')
 await h.state.load();assert.equal(h.reads.length,1)
 h.hooks.deactivate();h.visible.value=true;assert.equal(h.reads.length,1)
 h.hooks.activate();assert.equal(h.reads.length,2)
 h.reads[1].resolve({rows:revisions,total:2});await tick()
 assert.equal(h.state.selected.value.id,'r2');assert.equal(h.state.selectedVersion.value,'v3')
 h.media.at(-1).resolve({});await tick();assert.equal(h.state.preview.value,'blob:history')
 h.visible.value=false;assert.deepEqual(h.revoked,['blob:history']);h.close()
})
test('历史权限变化清空选中修订图片，旧响应不回填，退出后禁止读取',async()=>{
 const h=setup();h.visible.value=true;h.reads[0].resolve({rows:revisions,total:2});await tick()
 h.auth.user.permissions=[];assert.equal(h.state.selected.value,undefined);assert.equal(h.state.selectedVersion.value,'')
 assert.equal(h.reads.length,2);assert.equal(h.media[0].args[2].aborted,true)
 h.auth.token='';assert.equal(h.reads[1].args[2].aborted,true)
 h.reads[1].resolve({rows:revisions,total:2});h.media[0].resolve({});await tick()
 assert.equal(h.state.rows.value.length,0);assert.equal(h.state.total.value,0);assert.equal(h.state.preview.value,'')
 await h.state.load();assert.equal(h.reads.length,2);h.close()
})
