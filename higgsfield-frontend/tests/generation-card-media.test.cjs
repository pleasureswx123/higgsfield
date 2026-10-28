const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
const tick=()=>new Promise(setImmediate)
test('图片缩略图未就绪时不回退下载原图，手动重试可恢复',async()=>{
 const h=setup();h.visible.value=true
 h.calls[0].reject(new Error('图片缩略图尚未生成或不可用'));await tick()
 assert.equal(h.calls.length,1);assert.equal(h.state.url.value,'');assert.match(h.state.error.value,/尚未生成/)
 const pending=h.state.load();assert.equal(h.calls[1].kind,'thumbnail')
 h.calls[1].resolve({type:'image/webp'});await pending
 assert.equal(h.state.url.value,'blob:preview');assert.equal(h.state.error.value,'');h.close()
})
function setup(kind='image'){
 const exports={},calls=[],revoked=[],hooks={},auth=vue.reactive({token:'one',user:{permissions:[]}}),preview=vue.ref({outputId:'9007199254740993',revision:'1',kind}),visible=vue.ref(false)
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useGenerationCardMedia.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Error,AbortController,URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL:url=>revoked.push(url)},require(id){
  if(id==='vue')return {...vue,onActivated:fn=>{hooks.activate=fn},onDeactivated:fn=>{hooks.deactivate=fn},onBeforeUnmount:fn=>{hooks.close=fn}}
  if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
  return {getOutputThumbnail:(id,signal)=>new Promise((resolve,reject)=>calls.push({args:[id,false,signal],kind:'thumbnail',resolve,reject})),getOutputMedia:(...args)=>new Promise((resolve,reject)=>calls.push({args,kind:'original',resolve,reject}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useGenerationCardMedia(()=>preview.value,()=>visible.value))
 return {state,calls,revoked,hooks,auth,preview,visible,close(){hooks.close();scope.stop()}}
}
test('卡片图片按视口读取，修订切换取消旧请求，隐藏及撤权释放地址',async()=>{
 const h=setup();assert.equal(h.calls.length,0)
 h.visible.value=true;assert.equal(h.calls[0].args[0],'9007199254740993');assert.equal(h.calls[0].args[1],false);assert.equal(h.calls[0].kind,'thumbnail')
 h.preview.value={...h.preview.value,revision:'2'};assert.equal(h.calls[0].args[2].aborted,true)
 h.calls[0].resolve({type:'image/webp'});await tick();assert.equal(h.state.url.value,'')
 h.calls[1].resolve({type:'image/webp'});await tick();assert.equal(h.state.url.value,'blob:preview')
 h.auth.token='';assert.equal(h.state.url.value,'');assert.equal(h.revoked.length,1)
 h.auth.token='two';h.visible.value=false;assert.equal(h.calls.at(-1).args[2].aborted,true)
 h.close();await h.state.load();assert.equal(h.state.url.value,'')
})
test('视频不自动下载，主动预览验证类型，缓存恢复也不自动重新读取视频',async()=>{
 const h=setup('video');h.visible.value=true;assert.equal(h.calls.length,0)
 let loading=h.state.load();assert.equal(h.calls[0].kind,'original');h.calls[0].resolve({type:'text/html'});await loading
 assert.match(h.state.error.value,/媒体类型/);assert.equal(h.state.url.value,'')
 loading=h.state.load();h.calls[1].resolve({type:'video/mp4'});await loading
 assert.equal(h.state.url.value,'blob:preview')
 h.hooks.deactivate();assert.equal(h.state.url.value,'');assert.equal(h.revoked.length,1)
 h.hooks.activate();assert.equal(h.calls.length,2);h.close()
})

test('浏览器解码失败释放当前地址并允许重试，旧媒体错误不清除新预览',async()=>{
 const h=setup();h.visible.value=true
 h.calls[0].resolve({type:'image/webp'});await tick()
 h.state.mediaFailed('blob:old');assert.equal(h.state.url.value,'blob:preview')
 h.state.mediaFailed('blob:preview');assert.equal(h.state.url.value,'');assert.equal(h.revoked.length,1)
 assert.match(h.state.error.value,/解码/)
 const pending=h.state.load();h.calls[1].resolve({type:'image/webp'});await pending
 assert.equal(h.state.error.value,'');assert.equal(h.state.url.value,'blob:preview')
 h.close();h.state.mediaFailed('blob:preview');assert.equal(h.state.error.value,'')
})
