const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code=code; this.errorCode=errorCode } }
function setup(deferredReads=false, initiallyVisible=true){
 const visible=vue.ref(initiallyVisible)
 const exports={},auth=vue.reactive({token:'one',user:{permissions:['asset:read']}}),confirmations=[],calls=[],reads=[],hooks={};let changed=0
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useAssetActions.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{
  exports,Error,AbortController,crypto:{randomUUID:()=> 'key'},require(id){
   if(id==='vue')return {...vue,onBeforeUnmount:fn=>{hooks.close=fn},onActivated:fn=>{hooks.activate=fn},onDeactivated:fn=>{hooks.deactivate=fn}}
   if(id==='vue-router')return {onBeforeRouteLeave:fn=>{hooks.leave=fn},onBeforeRouteUpdate:fn=>{hooks.update=fn}}
   if(id==='element-plus')return {ElMessageBox:{confirm:()=>new Promise(resolve=>confirmations.push(resolve))}}
   if(id==='@/api/client')return {ApiError}
   if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
   return {renameAsset:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject})),recycleAsset:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject})),listAssetTrash:(...args)=>new Promise(resolve=>{reads.push({args,resolve});if(!deferredReads)resolve({rows:[],total:0})})}
  }
 })
 const scope=vue.effectScope(),state=scope.run(()=>exports.useAssetActions('99',()=>changed++,()=>visible.value))
 return {state,visible,auth,confirmations,calls,reads,hooks,changed:()=>changed,close(){hooks.close();scope.stop()}}
}
const tick=async()=>{await vue.nextTick();await new Promise(setImmediate)}
test('确认期间退出不发请求，过期项不进入恢复确认',async()=>{
 const h=setup(),item={id:'1',targetId:'9',revision:'2',name:'素材',canRestore:true}
 const op=h.state.lifecycle(item,true);h.auth.token='';h.confirmations[0]();await op
 assert.equal(h.calls.length,0);assert.equal(h.state.trashOpen.value,false)
 h.auth.token='two';await h.state.lifecycle({...item,canRestore:false},true)
 assert.equal(h.confirmations.length,1);h.close()
})
test('恢复使用确认前快照，账号切换后的迟到成功不刷新新账号',async()=>{
 const h=setup(),item={id:'1',targetId:'9007199254740993',revision:'2',name:'素材',canRestore:true}
 const op=h.state.lifecycle(item,true);item.revision='8';h.confirmations[0]();await tick()
 assert.equal(h.calls[0].args[1],'2');h.auth.token='two';h.calls[0].resolve({});await op
 assert.equal(h.changed(),0);assert.equal(h.state.pending.value,false);h.close()
})
test('重命名校验期间切换账号不写入，编辑副本不随外部修订变化',async()=>{
 const h=setup(),asset={id:'9',revision:'2',name:'旧名'}
 h.state.edit(asset);asset.revision='8';assert.equal(h.state.editing.value.revision,'2')
 let valid;h.state.form.value={validate:()=>new Promise(resolve=>{valid=resolve})}
 const op=h.state.save();h.auth.token='two';valid(true);await op
 assert.equal(h.calls.length,0);assert.equal(h.state.editing.value,null);h.close()
})


test('恢复确认锁定重复操作与页内跳转，缓存停用后旧确认不提交',async()=>{
 const h=setup(),item={id:'1',targetId:'9',revision:'2',name:'素材',canRestore:true}
 const op=h.state.lifecycle(item,true)
 assert.equal(h.state.pending.value,true);assert.equal(await h.hooks.leave(),false)
 assert.equal(await h.hooks.update({fullPath:'/p?tab=other'},{fullPath:'/p?tab=assets'}),false)
 await h.state.lifecycle(item,true);assert.equal(h.confirmations.length,1)
 h.hooks.deactivate();h.hooks.activate();h.confirmations[0]();await op
 assert.equal(h.calls.length,0);assert.equal(h.state.pending.value,false);h.close()
})

test('缓存停用保留重命名输入但不读取或写入，后台成功在激活时刷新一次',async()=>{
 const h=setup(true),asset={id:'9',revision:'2',name:'旧名'}
 h.state.edit(asset);h.state.draft.name='新名';h.state.trashOpen.value=true
 assert.equal(h.reads.length,1);h.hooks.deactivate()
 assert.equal(h.reads[0].args[2].aborted,true);assert.equal(h.state.draft.name,'新名')
 h.state.form.value={validate:async()=>true};await h.state.save();await h.state.refreshTrash()
 assert.equal(h.calls.length,0);assert.equal(h.reads.length,1)
 h.hooks.activate();assert.equal(h.reads.length,2)
 const save=h.state.save();await tick();h.hooks.deactivate()
 h.calls[0].resolve({});await save
 assert.equal(h.changed(),0);assert.equal(h.state.editing.value,null)
 h.hooks.activate();h.hooks.activate();assert.equal(h.changed(),1);assert.equal(h.reads.length,3)
 h.close()
})

test('回收站恢复末页后回退并等待有效页，无记录时不重复查询',async()=>{
 const h=setup(true)
 h.state.trashOpen.value=true;h.reads[0].resolve({rows:[{id:'first'}],total:31});await tick()
 h.state.page.value=2;h.reads[1].resolve({rows:[{id:'last'}],total:31});await tick()
 let done=false;const refresh=h.state.refreshTrash().then(()=>{done=true})
 h.reads[2].resolve({rows:[],total:30});await tick()
 assert.equal(h.state.page.value,1);assert.equal(h.reads.length,4);assert.equal(done,false)
 assert.equal(h.reads[3].args[1],1);assert.equal(h.state.trashLoading.value,true)
 h.reads[3].resolve({rows:[{id:'remaining'}],total:30});await refresh
 assert.equal(h.state.recycled.value[0].id,'remaining');assert.equal(h.state.trashLoading.value,false)
 h.state.page.value=2;h.reads[4].resolve({rows:[],total:0});await tick()
 assert.equal(h.state.page.value,1);assert.equal(h.state.recycled.value.length,0);assert.equal(h.reads.length,5)
 h.close()
})

test('权限变化丢弃旧编辑授权并重新读取回收站，旧确认与迟到响应不能回填',async()=>{
 const h=setup(true),item={id:'1',targetId:'9',revision:'2',name:'素材',canRestore:true}
 h.state.edit({id:'9',revision:'2',name:'旧名'});h.state.trashOpen.value=true
 const op=h.state.lifecycle(item,true)
 h.auth.user.permissions=[]
 assert.equal(h.state.editing.value,null);assert.equal(h.reads.length,2)
 assert.equal(h.reads[0].args[2].aborted,true)
 h.confirmations[0]();await op;assert.equal(h.calls.length,0)
 h.reads[1].resolve({rows:[],total:0});await tick()
 h.reads[0].resolve({rows:[{id:'old'}],total:1});await tick()
 assert.equal(h.state.recycled.value.length,0);h.close()
})


test('重命名未知结果固定名称修订与键，禁止取消或删除，成功后刷新', async () => {
 const h=setup(); h.state.edit({id:'9',revision:'2',name:'旧名'}); h.state.draft.name='新名'
 h.state.form.value={validate:async()=>true}
 const first=h.state.save(); await tick(); h.calls[0].reject(new Error('断网')); await first
 assert.equal(h.state.renameUncertain.value,true); await h.state.cancelEdit(); assert.notEqual(h.state.editing.value,null)
 await h.state.lifecycle({id:'9',revision:'2',name:'旧名'},false); assert.equal(h.confirmations.length,0)
 h.state.draft.name='意外修改'; h.state.editing.value.revision='8'
 const retry=h.state.save(); await tick()
 assert.equal(h.calls[1].args[0].revision,'2'); assert.equal(h.calls[1].args[1],'新名'); assert.equal(h.calls[1].args[2],h.calls[0].args[2])
 h.calls[1].resolve({}); await retry; assert.equal(h.state.renameUncertain.value,false); assert.equal(h.changed(),1); h.close()
})

test('重命名校验不提交后选对象或变化名称，取消确认后保留草稿', async () => {
 const h=setup(); h.state.edit({id:'9',revision:'2',name:'旧名'})
 let resolve; h.state.form.value={validate:()=>new Promise(done=>{resolve=done})}
 const first=h.state.save(); h.state.edit({id:'10',revision:'1',name:'另一素材'}); resolve(true); await first; assert.equal(h.calls.length,0)
 const second=h.state.save(); h.state.draft.name='新输入'; resolve(true); await second; assert.equal(h.calls.length,0)
 const cancel=h.state.cancelEdit(); h.hooks.deactivate(); h.hooks.activate(); h.confirmations[0](); await cancel
 assert.equal(h.state.draft.name,'新输入'); h.close()
})

test('明确重命名拒绝解除未知锁定且保留名称，账号变化清除原请求', async () => {
 const h=setup(); h.state.edit({id:'9',revision:'2',name:'旧名'}); h.state.draft.name='保留名称'; h.state.form.value={validate:async()=>true}
 const first=h.state.save(); await tick(); h.calls[0].reject(new ApiError('冲突',601,'REVISION_CONFLICT')); await first
 assert.equal(h.state.renameLocked.value,false); assert.equal(h.state.draft.name,'保留名称')
 const second=h.state.save(); await tick(); h.auth.token='two'; h.calls[1].resolve({}); await second
 assert.equal(h.state.renameUncertain.value,false); assert.equal(h.changed(),0); h.close()
})


test('删除恢复未知结果保留原对象修订和方向，重试无需第二次确认', async () => {
 for (const restore of [false,true]) {
  const h=setup(), item={id:'1',targetId:'9',revision:'2',name:'素材',canRestore:true}
  const first=h.state.lifecycle(item,restore); h.confirmations[0](); await tick()
  h.calls[0].reject(new Error('响应丢失')); await first
  assert.equal(h.state.lifecycleUncertain.value,true); assert.equal(await h.hooks.leave(),false)
  h.state.edit({id:'other',revision:'1',name:'其他'}); assert.equal(h.state.editing.value,null)
  item.revision='8'; await h.state.lifecycle(item,!restore); assert.equal(h.confirmations.length,1)
  h.hooks.deactivate(); await h.state.retryLifecycle(); assert.equal(h.calls.length,1); h.hooks.activate()
  const retry=h.state.retryLifecycle(); await tick()
  assert.deepEqual(h.calls[1].args,h.calls[0].args)
  h.calls[1].resolve({}); await retry
  assert.equal(h.state.actionsLocked.value,false); assert.equal(h.changed(),1); h.close()
 }
})

test('删除明确拒绝解除锁定，重试期间切换账号不回填', async () => {
 const h=setup(), item={id:'9',revision:'2',name:'素材'}
 const first=h.state.lifecycle(item,false); h.confirmations[0](); await tick()
 h.calls[0].reject(new ApiError('禁止删除',403,'FORBIDDEN')); await first
 assert.equal(h.state.lifecycleUncertain.value,false)
 const second=h.state.lifecycle(item,false); h.confirmations[1](); await tick()
 h.calls[1].reject(new Error('中断')); await second
 const retry=h.state.retryLifecycle(); await tick(); h.auth.token='two'; h.calls[2].resolve({}); await retry
 assert.equal(h.changed(),0); assert.equal(h.state.lifecycleLabel.value,''); assert.equal(h.state.actionsLocked.value,false); h.close()
})

test('素材页签显隐取消回收站读取并保留重命名草稿，缓存激活不能越过隐藏状态',async()=>{
 const h=setup(true,false)
 h.state.trashOpen.value=true;h.hooks.activate();assert.equal(h.reads.length,0)
 h.visible.value=true;assert.equal(h.reads.length,1)
 h.state.edit({id:'9',revision:'2',name:'旧名'});h.state.draft.name='保留草稿'
 h.visible.value=false
 assert.equal(h.state.active.value,false);assert.equal(h.reads[0].args[2].aborted,true)
 h.reads[0].resolve({rows:[{id:'stale'}],total:1});await tick()
 assert.equal(h.state.recycled.value.length,0);assert.equal(h.state.draft.name,'保留草稿')
 h.hooks.deactivate();h.visible.value=true;assert.equal(h.reads.length,1)
 h.hooks.activate();assert.equal(h.reads.length,2);assert.equal(h.state.draft.name,'保留草稿')
 h.close()
})

test('页签往返使旧删除确认失效，已提交重命名隐藏完成后返回只刷新一次',async()=>{
 const h=setup(),asset={id:'9',revision:'2',name:'旧名'}
 const remove=h.state.lifecycle(asset,false)
 h.visible.value=false;h.visible.value=true;h.confirmations[0]();await remove
 assert.equal(h.calls.length,0)
 h.state.edit(asset);h.state.draft.name='新名';h.state.form.value={validate:async()=>true}
 const save=h.state.save();await tick();h.visible.value=false
 h.calls[0].resolve({});await save;assert.equal(h.changed(),0)
 assert.equal(h.state.editing.value,null)
 h.visible.value=true;h.hooks.activate();assert.equal(h.changed(),1)
 h.close()
})
