const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const {webcrypto}=require('node:crypto'),ts=require('typescript'),vue=require('vue')
function setup(){
 const exports={},calls=[],hooks={},auth=vue.reactive({token:'one',user:{user:{userId:1},permissions:[]}})
 const output=vue.ref({id:'9007199254740993',revision:'4',workStatus:'none',allowedActions:['output:work-status']})
 let saved=0,closed=0
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useOutputStatus.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Error,AbortController,crypto:webcrypto,require(id){
  if(id==='vue')return {...vue,onBeforeUnmount:fn=>hooks.close=fn}
  if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
  return {updateOutputStatus:(...args)=>new Promise((resolve,reject)=>calls.push({args,resolve,reject}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useOutputStatus(()=>output.value,()=>saved++,()=>closed++))
 return {state,output,auth,calls,get saved(){return saved},get closed(){return closed},close(){hooks.close();scope.stop()}}
}
test('作品状态结果未知重试原请求，成功刷新并关闭，不丢字符串ID',async()=>{
 const h=setup();h.state.status.value='review';h.state.reason.value='说明'
 let operation=h.state.submit();await h.state.submit();assert.equal(h.calls.length,1)
 h.calls[0].reject(new Error('网络中断'));await operation
 assert.equal(h.state.retryable.value,true)
 h.state.status.value='approved';operation=h.state.submit()
 assert.equal(h.calls[1].args[0],'9007199254740993');assert.equal(h.calls[1].args[1].workStatus,'review')
 assert.equal(h.calls[1].args[2],h.calls[0].args[2]);h.calls[1].resolve({data:{}});await operation
 assert.equal(h.saved,1);assert.equal(h.closed,1);h.close()
})
test('明确修订冲突刷新但不覆盖，下一次保存使用当前修订与新键',async()=>{
 const h=setup();let operation=h.state.submit()
 h.calls[0].reject(Object.assign(new Error('修订冲突'),{code:601}));await operation
 assert.equal(h.saved,1);assert.equal(h.closed,0);assert.equal(h.state.retryable.value,false)
 h.output.value={...h.output.value,revision:'5'};h.state.reload();operation=h.state.submit()
 assert.equal(h.calls[1].args[1].revision,'5');assert.notEqual(h.calls[1].args[2],h.calls[0].args[2])
 h.calls[1].resolve({});await operation;h.close()
})
test('实时快照更新不静默升级正在编辑的基准修订',async()=>{
 const h=setup();h.state.status.value='approved'
 h.output.value={...h.output.value,revision:'5',workStatus:'rejected'}
 const operation=h.state.submit();assert.equal(h.calls[0].args[1].revision,'4')
 h.calls[0].reject(Object.assign(new Error('修订冲突'),{code:601}));await operation
 assert.equal(h.state.status.value,'approved');h.state.reload();assert.equal(h.state.status.value,'rejected');h.close()
})
test('表单校验期间切换身份不写入，输出消失关闭弹窗并隔离晚响应',async()=>{
 const h=setup();let validate
 let operation=h.state.submit(()=>new Promise(resolve=>validate=resolve))
 h.auth.token='two';validate(true);await operation;assert.equal(h.calls.length,0)
 operation=h.state.submit();h.output.value=undefined
 assert.equal(h.calls[0].args[3].aborted,true);h.calls[0].resolve({});await operation
 assert.equal(h.saved,0);assert.equal(h.closed,2);h.close()
})
