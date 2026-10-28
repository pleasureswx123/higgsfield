const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
const tick=()=>new Promise(setImmediate)
test('未就绪可重试，解码失败释放地址并忽略旧图片错误',async()=>{
 const h=setup();h.visible.value=true
 h.calls[0].reject(new Error('图片缩略图尚未生成或不可用'));await tick()
 assert.equal(h.calls.length,1);assert.match(h.state.error.value,/尚未生成/)
 const pending=h.state.load();h.calls[1].resolve({type:'image/webp'});await pending
 h.state.mediaFailed('blob:old');assert.equal(h.state.url.value,'blob:preview')
 h.state.mediaFailed('blob:preview');assert.equal(h.state.url.value,'');assert.equal(h.revoked.length,1)
 assert.match(h.state.error.value,/解码/);h.close()
})
function setup(allowOriginal = false){
 const exports={},calls=[],revoked=[],hooks={},auth=vue.reactive({token:'one',user:{permissions:[]}}),version=vue.ref('11'),visible=vue.ref(false)
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useReferenceThumbnail.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Error,AbortController,URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL:url=>revoked.push(url)},require(id){
  if(id==='vue')return {...vue,onActivated:fn=>{hooks.activate=fn},onDeactivated:fn=>{hooks.deactivate=fn},onBeforeUnmount:fn=>{hooks.close=fn}}
  if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
  return {readThumbnail:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject})),readMedia:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject,original:true}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useReferenceThumbnail(()=>version.value,()=>visible.value,()=>allowOriginal))
 return {state,calls,revoked,hooks,auth,version,visible,close(){hooks.close();scope.stop()}}
}
test('缩略图只在可见时读取授权固定版本，隐藏与卸载释放媒体',async()=>{
 const h=setup();assert.equal(h.calls.length,0)
 h.visible.value=true;assert.equal(h.calls[0].args[0],'11');assert.equal(h.calls[0].args.length,2)
 h.calls[0].resolve({type:'image/webp'});await tick();assert.equal(h.state.url.value,'blob:preview')
 h.visible.value=false;assert.equal(h.state.url.value,'');assert.equal(h.revoked.length,1)
 h.visible.value=true;h.calls[1].resolve({type:'image/webp'});await tick();h.close();assert.equal(h.revoked.length,2)
})
test('换版本、撤权和缓存停用阻断迟到缩略图，非图片显示错误',async()=>{
 const h=setup();h.visible.value=true;h.version.value='12'
 assert.equal(h.calls[0].args[1].aborted,true);h.calls[0].resolve({type:'image/webp'});await tick();assert.equal(h.state.url.value,'')
 h.calls[1].resolve({type:'application/json'});await tick();assert.match(h.state.error.value,/不是可显示/)
 h.auth.user.permissions=['asset:read'];assert.equal(h.calls.length,3)
 h.hooks.deactivate();h.calls[2].resolve({type:'image/webp'});await tick();assert.equal(h.state.url.value,'')
 h.hooks.activate();assert.equal(h.calls.length,4);h.auth.token='';h.calls[3].resolve({type:'image/webp'});await tick()
 assert.equal(h.state.url.value,'');h.close()
})


test('仅派生图未就绪时允许小图片回退授权预览，权限错误不回退', async () => {
 const h=setup(true);h.visible.value=true
 h.calls[0].reject(Object.assign(new Error('未就绪'),{errorCode:'THUMBNAIL_NOT_READY'}));await tick()
 assert.equal(h.calls[1].original,true);assert.equal(h.calls[1].args[1],false)
 h.calls[1].resolve({type:'image/png'});await tick();assert.equal(h.state.url.value,'blob:preview')
 const pending=h.state.load();h.calls[2].reject(Object.assign(new Error('无权限'),{code:403}));await pending
 assert.equal(h.calls.length,3);assert.equal(h.state.url.value,'');h.close()
})
