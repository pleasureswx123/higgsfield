const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
function setup(){
 const exports={},calls=[],auth=vue.reactive({token:'t',user:{user:{userId:1},permissions:[]}}),project=vue.ref('2');let fail=true,cleanup
 runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/composables/usePickerElementCopy.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,Error,crypto:{randomUUID:()=> '12345678-1234'},require(id){
 if(id==='vue')return {...vue,onBeforeUnmount:fn=>cleanup=fn}
 if(id.includes('stores/auth'))return {useAuthStore:()=>auth}
 if(id.includes('api/elements'))return {copyElement:async(...args)=>{calls.push(args);return {data:{id:'30'}}}}
 return {searchReferences:async()=>{if(fail)throw new Error('暂时不可读');return {rows:[{id:'30',projectId:'2',assetVersionIds:['40']}]}}}
 }})
 const scope=vue.effectScope(),state=scope.run(()=>exports.usePickerElementCopy(()=>project.value))
 return {state,calls,project,succeed(){fail=false},close(){cleanup();scope.stop()}}
}
const source={id:'10',projectId:'1',elementRevisionId:'11',alias:'hero',displayName:'角色'}
test('复制成功后读取失败，重试复用目标元素，不重复创建',async()=>{const h=setup();assert.equal(await h.state.resolve(source),null);assert.equal(h.calls.length,1);h.succeed();const row=await h.state.resolve(source);assert.equal(row.id,'30');assert.equal(h.calls.length,1);assert.equal(h.calls[0][1].targetProjectId,'2');assert.equal(h.calls[0][1].sourceRevisionId,'11');h.close()})
test('当前项目直接引用，不触发复制；切换项目清除旧复制意图',async()=>{const h=setup();const local={...source,projectId:'2'};assert.equal(await h.state.resolve(local),local);assert.equal(h.calls.length,0);await h.state.resolve(source);h.project.value='3';await h.state.resolve(source);assert.equal(h.calls.length,2);assert.equal(h.calls[1][1].targetProjectId,'3');h.close()})
