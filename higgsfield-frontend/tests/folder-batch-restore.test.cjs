const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function setup(action, confirm = async () => {}, kind = 'Folder', operation = 'Restore', selection) {
 const exports = {}, calls = [], auth = vue.reactive({token:'one'}), rows = vue.ref([
  {id:'1',targetId:'9007199254740993',revision:'2',name:'一',canRestore:true},
  {id:'2',targetId:'9007199254740994',revision:'3',name:'二',canRestore:true},
  {id:'3',targetId:'5',revision:'1',name:'过期',canRestore:false},
 ]), allowed = vue.ref(true), hooks = {}; let keys=0, refreshes=0
 class ApiError extends Error {}
 const requireTool = id => {
   if(id==='vue')return {...vue,onBeforeUnmount:fn=>{hooks.close=fn},onActivated:fn=>{hooks.activate=fn},onDeactivated:fn=>{hooks.deactivate=fn}}
   if(id==='vue-router')return {onBeforeRouteLeave:fn=>{hooks.leave=fn},onBeforeRouteUpdate(){}}
   if(id==='element-plus')return {ElMessageBox:{confirm}}
   if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
   if(id.includes('api/client'))return {ApiError}
   if(id==='./useBatchRestore') return load('useBatchRestore')
   if(id==='./useBatchAction') return load('useBatchAction')
   return {recycleElement:async(...args)=>{calls.push(args);return action(args,calls.length)},actOnFolder:async(...args)=>{calls.push(args);return action(args,calls.length)},recycleAsset:async(...args)=>{calls.push(args);return action(args,calls.length)}}
 }
 function load(name) {
  const result={}
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname,`../src/composables/${name}.ts`),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:result,crypto:{randomUUID:()=>String(++keys)},require:requireTool})
  return result
 }
 Object.assign(exports,load(`use${kind}Batch${operation}`))
 const scope=vue.effectScope(), state=scope.run(()=>exports[`use${kind}Batch${operation}`](()=>rows.value,()=>allowed.value,async()=>{refreshes++},selection))
 return {state,calls,auth,rows,allowed,hooks,refreshes:()=>refreshes,close(){hooks.close();scope.stop()}}
}
test('批量恢复只选有效项，部分失败重试原快照和键，不重复恢复成功项',async()=>{
 const h=setup(async(args,count)=>{if(count===2)throw Error('断网')})
 h.state.selectAll(true); assert.equal(h.state.selected.value.length,2)
 await h.state.restore(); assert.equal(h.calls.length,2);assert.equal(h.state.selected.value[0],'2')
 h.rows.value[1].revision='9';await h.state.restore()
 assert.equal(h.calls.length,3);assert.equal(h.calls[2][0],'9007199254740994')
 assert.equal(h.calls[2][2].revision,'3');assert.equal(h.calls[2][3],h.calls[1][3])
 assert.equal(h.state.selected.value.length,0);assert.equal(h.refreshes(),2);h.close()
})

test('素材批量恢复调用素材接口并保留原修订重试，不重复成功项',async()=>{
 const h=setup(async(args,count)=>{if(count===2)throw Error('断网')},async()=>{},'Asset')
 h.state.selectAll(true);await h.state.restore()
 assert.equal(h.calls[0][0],'9007199254740993');assert.equal(h.calls[0][1],'2');assert.equal(h.calls[0][2],true)
 h.rows.value[1].revision='9';await h.state.restore()
 assert.equal(h.calls.length,3);assert.equal(h.calls[2][1],'3');assert.equal(h.calls[2][3],h.calls[1][3])
 assert.equal(h.state.selected.value.length,0);assert.match(h.state.message.value,/素材/);h.close()
})
test('确认期间切换账号不发送请求，恢复中撤权停止后续项',async()=>{
 let confirm
 const h=setup(async()=>{},()=>new Promise(done=>{confirm=done}))
 h.state.selectAll(true);const run=h.state.restore();assert.equal(h.hooks.leave(),false)
 h.auth.token='';confirm();await run;assert.equal(h.calls.length,0);assert.equal(h.hooks.leave(),true);h.close()
 let c
 c=setup(async()=>{c.allowed.value=false});c.state.selectAll(true);await c.state.restore()
 assert.equal(c.calls.length,1);assert.equal(c.state.selected.value.length,1);c.close()
})

test('元素批量恢复适配元素接口，保留字符串身份和原修订重试',async()=>{
 const h=setup(async(args,count)=>{if(count===2)throw Error('断网')},async()=>{},'Element')
 h.state.selectAll(true);await h.state.restore();h.rows.value[1].revision='9';await h.state.restore()
 assert.equal(h.calls.length,3);assert.equal(h.calls[2][0],'9007199254740994')
 assert.equal(h.calls[2][1],'3');assert.equal(h.calls[2][2],true);assert.equal(h.calls[2][3],h.calls[1][3])
 assert.match(h.state.message.value,/元素/);h.close()
})

test('页面停用后不继续批量写入，重新激活可手动处理剩余项',async()=>{
 let h
 h=setup(async(args,count)=>{if(count===1)h.hooks.deactivate()})
 h.state.selectAll(true);await h.state.restore()
 assert.equal(h.calls.length,1);assert.equal(h.refreshes(),0);assert.equal(h.state.selected.value.length,1)
 await h.state.restore();assert.equal(h.calls.length,1)
 h.hooks.activate();await h.state.restore();assert.equal(h.calls.length,2);assert.equal(h.state.selected.value.length,0)
 h.close()
})


test('元素批量删除保留原修订与幂等键，部分失败只重试失败项', async () => {
 const h=setup(async(args,count)=>{if(count===2)throw Error('断网')},async()=>{},'Element','Delete')
 h.rows.value[2].allowedActions=['element:read']
 h.state.selectAll(true); assert.equal(h.state.selected.value.length,2)
 await h.state.execute()
 assert.equal(h.calls.length,2);assert.equal(h.calls[0][0],'1');assert.equal(h.calls[0][2],false)
 h.rows.value[1].revision='9';await h.state.execute()
 assert.equal(h.calls.length,3);assert.equal(h.calls[2][0],'2');assert.equal(h.calls[2][1],'3')
 assert.equal(h.calls[2][3],h.calls[1][3]);assert.equal(h.state.selected.value.length,0)
 assert.match(h.state.message.value,/已删除 1 个元素/);h.close()
})

test('批量删除确认期间换账号取消写入，执行中撤权保留未执行项', async () => {
 let confirm
 const h=setup(async()=>{},()=>new Promise(done=>{confirm=done}),'Element','Delete')
 h.state.selectAll(true);const pending=h.state.execute();assert.equal(h.hooks.leave(),false)
 h.auth.token='two';confirm();await pending
 assert.equal(h.calls.length,0);assert.equal(h.state.selected.value.length,0);h.close()
 let c
 c=setup(async()=>{c.allowed.value=false},async()=>{},'Element','Delete')
 c.state.selectAll(true);await c.state.execute()
 assert.equal(c.calls.length,1);assert.equal(c.state.selected.value.length,2)
 assert.match(c.state.message.value,/剩余 2 项未执行/);c.close()
})

test('素材批量删除按素材身份去重，仅选择有删除权限项并保留原修订重试', async () => {
 const h=setup(async(args,count)=>{if(count===2)throw Error('断网')},async()=>{},'Asset','Delete')
 h.rows.value[0].allowedActions=['asset:remove'];h.rows.value[1].allowedActions=['asset:remove']
 h.rows.value.push({...h.rows.value[0]})
 h.state.selectAll(true);assert.equal(h.state.selected.value.length,2)
 await h.state.execute();assert.equal(h.calls.length,2);assert.equal(h.calls[0][2],false)
 h.rows.value[1].revision='99';await h.state.execute()
 assert.equal(h.calls.length,3);assert.equal(h.calls[2][0],'2');assert.equal(h.calls[2][1],'3')
 assert.equal(h.calls[2][3],h.calls[1][3]);assert.equal(h.state.selected.value.length,0)
 assert.match(h.state.message.value,/已删除 1 个素材/);h.close()
})


test('共用选择时删除只移除成功项，保留无删除权限的下载选择', async () => {
 const selection=vue.ref(['1','2'])
 const h=setup(async()=>{},async()=>{},'Asset','Delete',selection)
 h.rows.value[0].allowedActions=['asset:remove'];h.rows.value[1].allowedActions=['asset:read','asset:download']
 await h.state.execute()
 assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'1')
 assert.equal(selection.value.length,1);assert.equal(selection.value[0],'2');h.close()
})

test('元素删除与移动共用选择，删除完成保留仅有编辑权限的选择', async () => {
 const selection=vue.ref(['1','2'])
 const h=setup(async()=>{},async()=>{},'Element','Delete',selection)
 h.rows.value[0].allowedActions=['element:remove'];h.rows.value[1].allowedActions=['element:read','element:edit']
 await h.state.execute();assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'1')
 assert.equal(selection.value.length,1);assert.equal(selection.value[0],'2');h.close()
})

test('批量操作确认期间隐藏再返回，旧确认仍不能提交',async()=>{
 let confirm
 const h=setup(async()=>{},()=>new Promise(resolve=>{confirm=resolve}),'Asset')
 h.state.selectAll(true);const run=h.state.restore()
 h.allowed.value=false;h.allowed.value=true;confirm();await run
 assert.equal(h.calls.length,0);assert.equal(h.state.pending.value,false)
 assert.equal(h.state.selected.value.length,2);h.close()
})

test('批次执行中隐藏再返回也停止后续项，已成功项不重复处理',async()=>{
 let h
 h=setup(async(args,count)=>{if(count===1){h.allowed.value=false;h.allowed.value=true}},async()=>{},'Asset')
 h.state.selectAll(true);await h.state.restore()
 assert.equal(h.calls.length,1);assert.equal(h.state.selected.value.length,1)
 assert.match(h.state.message.value,/剩余 1 项未执行/)
 await h.state.restore();assert.equal(h.calls.length,2)
 assert.equal(h.calls[1][0],'9007199254740994');h.close()
})
