const { test } = require('node:test'), assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'), { join } = require('node:path'), { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue'), tick = () => new Promise(setImmediate)
function setup(name) {
 const exports={},hooks={},requests=[],pushes=[]
 const auth=vue.reactive({token:'one',user:{permissions:[]}}),route=vue.reactive({params:{id:'99'},query:{targetElement:'9007199254740993',returnTo:'elements'}})
 const source={id:'9007199254740993',projectId:'99',name:'主角',alias:'hero',allowedActions:['element:edit']}
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,`../src/composables/${name}.ts`),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
 exports,Error,AbortController,require(id){
 if(id==='vue')return {...vue,onActivated:fn=>{hooks.activate=fn},onDeactivated:fn=>{hooks.deactivate=fn},onBeforeUnmount:fn=>{hooks.close=fn}}
 if(id==='vue-router')return {useRoute:()=>route,useRouter:()=>({push:async value=>pushes.push(value)})}
 if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
 return {readElement:(id,signal)=>new Promise(resolve=>requests.push({kind:'element',id,signal,resolve})),readBrief:(id,signal)=>new Promise(resolve=>requests.push({kind:'brief',id,signal,resolve}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports[name]('99'))
 function resolve(start=0,element=source,actions=['generation:create','asset:create']) { requests[start].resolve({data:{element}});requests[start+1].resolve({data:{allowedActions:actions}}) }
 return {state,source,requests,pushes,route,auth,hooks,resolve,close(){hooks.close();scope.stop()}}
}
test('我的元素入口核验双向权限，携带字符串目标及固定返回标识，不发送生成',async()=>{
 const h=setup('useElementGenerationEntry'),run=h.state.start(h.source)
 assert.equal(h.state.pending.value,true);await h.state.start(h.source);assert.equal(h.requests.length,2)
 h.resolve();await run;assert.equal(h.pushes[0].params.id,'99');assert.equal(h.pushes[0].query.targetElement,'9007199254740993');assert.equal(h.pushes[0].query.returnTo,'elements');h.close()
})
test('入口拒绝只读或缺少目标素材创建权限，账号切换阻断迟到跳转',async()=>{
 const h=setup('useElementGenerationEntry');let run=h.state.start(h.source)
 h.resolve(0,{...h.source,allowedActions:[]});await run;assert.equal(h.pushes.length,0)
 run=h.state.start(h.source);h.resolve(2,h.source,['generation:create']);await run;assert.equal(h.pushes.length,0)
 run=h.state.start(h.source);h.auth.token='two';h.resolve(4);await run;assert.equal(h.pushes.length,0);assert.equal(h.state.error.value,'');h.close()
})
test('创作目标刷新重新核验，非法ID与跨项目拒绝，返回链接不接受任意地址',async()=>{
 const h=setup('useElementGenerationTarget');h.resolve();await tick();assert.equal(h.state.target.value.id,h.source.id)
 h.route.query.returnTo='https://evil.example';assert.equal(h.state.returnTo.value,'/projects/99?tab=elements')
 h.route.query.targetElement=['1','2'];assert.equal(h.state.target.value,undefined);assert.match(h.state.error.value,/标识无效/)
 h.route.query.targetElement='2';h.resolve(2,{...h.source,projectId:'100'});await tick();assert.equal(h.state.target.value,undefined);assert.match(h.state.error.value,/不属于/);h.close()
})
test('目标缓存停用、权限变化与账号切换清除旧目标并隔离迟到读取',async()=>{
 const h=setup('useElementGenerationTarget');h.hooks.deactivate();h.resolve();await tick();assert.equal(h.state.target.value,undefined)
 h.hooks.activate();h.resolve(2);await tick();assert.equal(h.state.target.value.id,h.source.id)
 h.auth.user.permissions=['changed'];assert.equal(h.state.target.value,undefined)
 h.auth.token='two';h.resolve(4);await tick();assert.equal(h.state.target.value,undefined)
 h.resolve(6);await tick();assert.equal(h.state.target.value.id,h.source.id);h.close()
})
