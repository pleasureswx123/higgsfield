const { test } = require('node:test'), assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'), { join } = require('node:path'), { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue'), tick = () => new Promise(setImmediate)
function setup() {
 const exports={},hooks={},converts=[],saves=[],reads=[]
 const auth=vue.reactive({token:'one',user:{permissions:[]}})
 const stateData={element:{id:'9007199254740993',projectId:'99',name:'主角',alias:'hero',category:'character',workStatus:'working',performerId:'3',revision:'7',allowedActions:['element:edit']},currentRevision:{id:'701',description:'原描述',label:'原标签',propertyValues:[{definitionId:'31',definitionVersion:2,value:['A']}],media:[{assetVersionId:'11',ordinal:0,isPrimary:true}]}}
 const output={jobId:'50',kind:'image',archiveState:'archived',file:{state:'ready'},allowedActions:['output:to-asset']};let key=0
 class ApiError extends Error { constructor(message,code,errorCode){super(message);this.code=code;this.errorCode=errorCode} }
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/useOutputToElement.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
 exports,Error,AbortController,crypto:{randomUUID:()=>String(++key)},require(id){
 if(id==='vue')return {...vue,onActivated:fn=>{hooks.activate=fn},onDeactivated:fn=>{hooks.deactivate=fn},onBeforeUnmount:fn=>{hooks.close=fn}}
 if(id==='vue-router')return {onBeforeRouteLeave:fn=>{hooks.leave=fn},onBeforeRouteUpdate:fn=>{hooks.update=fn}}
 if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
 if(id.includes('client'))return {ApiError}
 return {readElement:async(id,signal)=>{reads.push({id,signal});return {data:stateData}},getOutput:async()=>({data:output}),readBrief:async()=>({data:{allowedActions:['asset:create']}}),outputToAsset:(...args)=>new Promise((resolve,reject)=>converts.push({args,resolve,reject})),saveElement:(...args)=>new Promise((resolve,reject)=>saves.push({args,resolve,reject}))}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useOutputToElement('60','50',{id:stateData.element.id,projectId:'99',name:'主角'}))
 const asset={id:'80',mediaType:'image',currentVersionId:'81'}
 return {state,stateData,output,converts,saves,reads,hooks,auth,ApiError,asset,close(){hooks.close();scope.stop()}}
}
test('归档作品两步写入保留字段和主图，保存未知结果只重放原快照原键',async()=>{
 const h=setup();await tick();const run=h.state.submit();await tick()
 h.converts[0].resolve({data:h.asset});await tick()
 const args=h.saves[0].args;assert.equal(args[1],'7');assert.equal(args[2].media.length,2);assert.equal(args[2].media[0].isPrimary,true);assert.equal(args[2].media[1].isPrimary,false)
 assert.equal(args[2].description,'原描述');assert.equal(args[2].propertyValues[0].value[0],'A');assert.equal(args[2].label,'原标签')
 h.saves[0].reject(new Error('断网'));await run;assert.equal(h.state.locked.value,true);assert.equal(h.hooks.leave(),false)
 h.stateData.element.revision='8';h.stateData.currentRevision.description='他人改动'
 const retry=h.state.submit();await tick();assert.equal(h.converts.length,1);assert.equal(h.saves[1].args[3],args[3]);assert.equal(h.saves[1].args[1],'7');assert.equal(h.saves[1].args[2].description,'原描述')
 h.saves[1].resolve({data:h.stateData});await retry;assert.ok(h.state.result.value);assert.equal(h.state.locked.value,false);h.close()
})
test('明确修订冲突重新读取并保留他人改动，复用已创建素材而不重复转换',async()=>{
 const h=setup();await tick();const run=h.state.submit();await tick();h.converts[0].resolve({data:h.asset});await tick()
 h.saves[0].reject(new h.ApiError('修订冲突',601,'REVISION_CONFLICT'));await run;assert.equal(h.state.locked.value,false)
 h.stateData.element.revision='8';h.stateData.currentRevision.description='新描述';h.stateData.currentRevision.media.push({assetVersionId:'12',ordinal:1,isPrimary:false})
 const retry=h.state.submit();await tick();assert.equal(h.converts.length,1);assert.equal(h.saves[1].args[1],'8');assert.equal(h.saves[1].args[2].description,'新描述');assert.equal(h.saves[1].args[2].media.length,3);assert.notEqual(h.saves[1].args[3],h.saves[0].args[3])
 h.saves[1].resolve({data:h.stateData});await retry;h.close()
})
test('素材创建未知结果保留键，停用不继续保存，恢复后空图目标设置主图',async()=>{
 const h=setup();await tick();h.stateData.currentRevision.media=[]
 let run=h.state.submit();await tick();h.converts[0].reject(new Error('超时'));await run
 run=h.state.submit();await tick();assert.equal(h.converts[1].args[2],h.converts[0].args[2]);h.hooks.deactivate();h.converts[1].resolve({data:h.asset});await run
 assert.equal(h.saves.length,0);assert.ok(h.state.asset.value);h.hooks.activate();await tick()
 run=h.state.submit();await tick();assert.equal(h.converts.length,2);assert.equal(h.saves[0].args[2].media[0].isPrimary,true)
 h.saves[0].resolve({data:h.stateData});await run;h.close()
})
test('未归档作品拒绝写入，账号变化隔离迟到素材，撤权不继续元素保存',async()=>{
 const h=setup();await tick();h.output.archiveState='archive_failed';await h.state.submit();assert.equal(h.converts.length,0)
 h.output.archiveState='archived';let run=h.state.submit();await tick();h.auth.token='two';h.converts[0].resolve({data:h.asset});await run;assert.equal(h.state.asset.value,undefined);assert.equal(h.saves.length,0)
 run=h.state.submit();await tick();h.auth.user.permissions=['changed'];h.converts[1].resolve({data:h.asset});await run;assert.equal(h.saves.length,0);h.close()
})
