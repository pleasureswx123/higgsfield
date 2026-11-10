const {test}=require('node:test')
const assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
test('人员搜索忽略迟到响应，分页追加且重置清除搜索',async()=>{
 const requests=[],exports={}
 const code=ts.transpileModule(readFileSync('src/composables/useMemberCandidates.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
 runInNewContext(code,{exports,setTimeout,clearTimeout,require(id){return id==='vue'?{...vue,onBeforeUnmount(){}}:{readMemberCandidates:(...args)=>new Promise(resolve=>requests.push({args,resolve}))}}})
 const scope=vue.effectScope(),s=scope.run(()=>exports.useMemberCandidates('2'))
 const a=s.load();s.keyword.value='甲';const b=s.load()
 requests[1].resolve({rows:[{userId:'2'}],hasNext:true});await b
 requests[0].resolve({rows:[{userId:'1'}],hasNext:false});await a
 assert.equal(s.items.value[0].userId,'2')
 const c=s.load(true);requests[2].resolve({rows:[{userId:'3'}],hasNext:false});await c
 assert.equal(s.items.value.length,2)
 s.reset();assert.equal(s.keyword.value,'');assert.equal(s.items.value.length,0)
 requests[3].resolve({rows:[],hasNext:false});await Promise.resolve()
 scope.stop()
})
