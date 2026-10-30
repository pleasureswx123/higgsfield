const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
function setup(){
 const exports={},calls=[],hooks={},auth=vue.reactive({token:'one',user:{user:{userId:1},permissions:['generation:create']}})
 const project=vue.ref('3'),disabled=vue.ref(false)
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useReferencePicker.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Error,AbortController,require(id){
  if(id==='vue')return {...vue,onActivated:fn=>hooks.activate=fn,onDeactivated:fn=>hooks.deactivate=fn,onBeforeUnmount:fn=>hooks.close=fn}
  if(id.includes('api/elements'))return {listElements:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject})),readElement:async id=>({data:{currentRevision:{id:'20',media:[{assetVersionId:'11',isPrimary:true}]}}})}
  if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
  return {searchReferences:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useReferencePicker(()=>project.value,()=>disabled.value))
 return {state,calls,hooks,auth,project,disabled,close(){hooks.close();scope.stop()}}
}
const row=(id='1',projectId='3')=>({id,projectId,kind:'element',elementRevisionId:'20',assetVersionIds:['11']})
const tick=()=>new Promise(resolve=>setImmediate(resolve))
async function resolve(h,index=0,rows=[row()]){h.calls[index].resolve({rows,total:rows.length});await tick()}
test('选择器仅在打开时查询，换页清空旧候选，迟到响应不覆盖新结果',async()=>{
 const h=setup();await h.state.load();assert.equal(h.calls.length,0)
 h.state.show();await resolve(h);const old=h.state.rows.value[0];assert.equal(h.state.canSelect(old),true)
 h.state.page.value=2;const pending=h.state.load();assert.equal(h.state.canSelect(old),false);assert.equal(h.state.total.value,0)
 h.state.search();await resolve(h,2,[row('2')]);await resolve(h,1,[row('3')]);await pending
 assert.equal(h.state.rows.value[0].id,'2');assert.equal(h.state.canSelect(row('2')),false);h.close()
})
test('账号、用户身份、权限及项目变化关闭并清空候选，旧请求取消',async()=>{
 for(const change of [h=>h.auth.token='two',h=>h.auth.user.user.userId=2,h=>h.auth.user.permissions=[],h=>h.project.value='4']){
  const h=setup();h.state.show();await resolve(h);const old=h.state.rows.value[0]
  const pending=h.state.load();change(h)
  assert.equal(h.state.open.value,false);assert.equal(h.state.canSelect(old),false);assert.equal(h.state.contextRevision.value,1)
  assert.equal(h.calls[1].args[1].aborted,true);await resolve(h,1);await pending
  assert.equal(h.state.rows.value.length,0);assert.equal(h.state.total.value,0);h.close()
 }
})
test('缓存停用和卸载隔离晚响应，恢复不自动打开，重开使用当前项目',async()=>{
 const h=setup();h.state.show();h.hooks.deactivate();await resolve(h)
 assert.equal(h.state.rows.value.length,0);h.state.show();assert.equal(h.calls.length,1)
 h.project.value='4';h.hooks.activate();assert.equal(h.state.open.value,false)
 h.state.show();assert.equal(h.calls[1].args[0].projectId,'4');await resolve(h,1,[row('2','4')])
 assert.equal(h.state.canSelect(h.state.rows.value[0]),true);h.close();assert.equal(h.state.rows.value.length,0)
})
test('禁用与退出不查询，恢复后必须重新打开；关闭不丢搜索条件',async()=>{
 const h=setup();h.state.q.value='角色';h.state.kind.value='element';h.disabled.value=true
 h.state.show();await h.state.load();assert.equal(h.calls.length,0)
 h.disabled.value=false;h.auth.token='';h.state.show();assert.equal(h.calls.length,0)
 h.auth.token='two';h.state.show();await resolve(h);h.state.close()
 assert.equal(h.state.rows.value.length,0);assert.equal(h.state.q.value,'角色');assert.equal(h.state.kind.value,'element');h.close()
})
test('当前失败清除计数并可重试，关闭后的失败不重新显示错误',async()=>{
 const h=setup();h.state.show();h.calls[0].reject(new Error('无读取权限'));await tick()
 assert.equal(h.state.error.value,'无读取权限');assert.equal(h.state.total.value,0)
 const pending=h.state.load();h.state.close();h.calls[1].reject(new Error('迟到错误'));await pending
 assert.equal(h.state.error.value,'');assert.equal(h.state.loading.value,false);h.close()
})

test('素材加号与元素引用入口分别查询对应类型，重新打开重置分页',async()=>{
 const h=setup()
 h.state.show('asset');assert.equal(h.calls[0].args[0].kind,'asset');await resolve(h,0,[])
 h.state.page.value=4;h.state.close();h.state.show('element')
 assert.equal(h.calls[1].args[0].kind,'element');assert.equal(h.calls[1].args[0].pageNum,1)
 await resolve(h,1,[]);h.close()
})

test('筛选在服务端分页前传递，元素查询不混入素材来源',async()=>{
 const h=setup();h.state.mediaType.value='video';h.state.source.value='uploaded';h.state.recent.value=true;h.state.sort.value='oldest'
 h.state.show('asset');assert.equal(h.calls[0].args[0].mediaType,'video');assert.equal(h.calls[0].args[0].source,'uploaded');assert.equal(h.calls[0].args[0].recent,true);assert.equal(h.calls[0].args[0].sort,'oldest');await resolve(h,0,[])
 h.state.category.value='character';h.state.show('element');assert.equal(h.calls[1].args[0].category,'character');assert.equal(h.calls[1].args[0].source,undefined);await resolve(h,1,[]);h.close()
})

 test('我的元素查询本人跨项目内容，仅允许当前查询返回的对象',async()=>{
 const h=setup();h.state.elementScope.value='mine';h.state.show('element');assert.equal(h.calls[0].args[0],undefined);assert.equal(h.calls[0].args[1].mineFilter,'created');
 await resolve(h,0,[{id:'1',projectId:'9',name:'外部角色',alias:'hero',category:'character'}]);
 await resolve(h,1,[{...row('1','9'),allowedMediaRoles:['reference_image']}]);
 assert.equal(h.state.rows.value[0].projectId,'9');assert.equal(h.state.canSelect(h.state.rows.value[0]),true);assert.equal(h.state.canSelect(row('1','9')),false);h.close()
 })
