const {test}=require('node:test'),assert=require('node:assert/strict')
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm')
const ts=require('typescript'),vue=require('vue')
function load(file,require){const exports={};runInNewContext(ts.transpileModule(readFileSync(join(__dirname,'../src/',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,require,Error,AbortController});return exports}
const utils=load('utils/draftReferences.ts',()=>({}))
const original=()=>[{referenceKey:'7',assetVersionId:'10',elementRevisionId:'20',mediaRole:'reference_image',ordinal:0}]
const candidate={kind:'element',id:'1',projectId:'3',elementRevisionId:'21',assetVersionIds:['11','12'],primaryAssetVersionId:'12',allowedMediaRoles:['reference_image','first_frame']}
test('元素默认主图，显式多选按修订顺序，空选或其他来源拒绝',()=>{
 const before=JSON.stringify(candidate)
 assert.deepEqual(Array.from(utils.selectReferenceMedia(candidate).assetVersionIds),['12'])
 const selected=utils.selectReferenceMedia(candidate,['12','11','12'])
 assert.deepEqual(Array.from(selected.assetVersionIds),['11','12'])
 assert.equal(utils.appendCandidate([],selected,'reference_image').length,2)
 assert.throws(()=>utils.selectReferenceMedia(candidate,[]),/有效图片/)
 assert.throws(()=>utils.selectReferenceMedia(candidate,['999']),/有效图片/)
 assert.equal(JSON.stringify(candidate),before)
})
test('升级保留引用编号、其他引用和输入对象，首帧使用新主图',()=>{
 const input=[...original(),{...original()[0],mediaRole:'first_frame',ordinal:1},{...original()[0],referenceKey:'8',ordinal:2}]
 const before=JSON.stringify(input),result=utils.upgradeReferenceGroup(input,'7','20',candidate)
 assert.equal(JSON.stringify(input),before);assert.deepEqual(Array.from(result,x=>x.assetVersionId),['11','12','12','10'])
 assert.deepEqual(Array.from(result,x=>x.referenceKey),['7','7','7','8']);assert.deepEqual(Array.from(result,x=>x.ordinal),[0,1,2,3])
})
test('模型容量、角色或来源变化阻止升级且保留原引用',()=>{
 const input=original(),before=JSON.stringify(input)
 assert.throws(()=>utils.upgradeReferenceGroup(input,'7','20',candidate,{referenceRules:{maxTotal:1,roles:{reference_image:{maxCount:1,mediaTypes:['image']}}}}),/数量/)
 assert.throws(()=>utils.upgradeReferenceGroup(input,'7','19',candidate),/引用已变化/)
 assert.throws(()=>utils.upgradeReferenceGroup(input,'7','20',{...candidate,allowedMediaRoles:[]}),/不兼容/)
 assert.equal(JSON.stringify(input),before)
})
function setup(){
 const calls=[],hooks={},auth=vue.reactive({token:'one',user:{user:{userId:1},permissions:[]}}),refs=vue.ref(original())
 const exports=load('composables/useReferenceUpdates.ts',id=>id==='vue'?{...vue,onActivated:fn=>hooks.activate=fn,onDeactivated:fn=>hooks.stop=fn,onBeforeUnmount:fn=>hooks.close=fn}:id.includes('stores/auth')?{useAuthStore:()=>auth}:id.includes('draftReferences')?utils:{checkReferenceUpdates:(...args)=>new Promise(resolve=>calls.push({args,resolve}))})
 const scope=vue.effectScope(),state=scope.run(()=>exports.useReferenceUpdates(()=>'3',refs,()=>false,()=>null))
 return {state,refs,auth,calls,hooks,close(){hooks.close();scope.stop()}}
}
async function ready(h,index=0){h.calls[index].resolve({data:{items:[{elementRevisionId:'20',state:'updated',candidate}]}});await new Promise(resolve=>setImmediate(resolve))}
test('检查不改引用，取消保留旧修订，确认后才替换',async()=>{
 const h=setup();await ready(h);assert.equal(h.refs.value[0].elementRevisionId,'20')
 await h.state.upgrade('7',async()=>false);assert.equal(h.refs.value.length,1)
 await h.state.upgrade('7',async()=>true);assert.equal(h.refs.value.length,2);assert.equal(h.refs.value[0].elementRevisionId,'21');h.close()
})
test('确认期间编辑或切换身份使升级失效，停用隔离晚响应',async()=>{
 const h=setup();await ready(h);let confirm
 let operation=h.state.upgrade('7',()=>new Promise(resolve=>confirm=resolve))
 h.refs.value=[{...h.refs.value[0],mediaRole:'first_frame'}];confirm(true);await operation;assert.equal(h.refs.value[0].elementRevisionId,'20')
 operation=h.state.upgrade('7',()=>new Promise(resolve=>confirm=resolve));h.auth.token='two';confirm(true);await operation
 assert.equal(h.refs.value[0].elementRevisionId,'20');h.hooks.stop();await ready(h,1)
 assert.equal(Object.keys(h.state.updates.value).length,0);assert.equal(h.calls[1].args[2].aborted,true);h.close()
})

test('图片追加多选，视频替换为单选且保留图片',()=>{
 const image={...candidate,kind:'asset',elementRevisionId:null,assetVersionIds:['30'],allowedMediaRoles:['reference_image']}
 const video={...image,assetVersionIds:['40'],allowedMediaRoles:['reference_video']}
 let refs=utils.selectCandidate([],image,'reference_image')
 refs=utils.selectCandidate(refs,{...image,assetVersionIds:['31']},'reference_image')
 refs=utils.selectCandidate(refs,video,'reference_video')
 const before=JSON.stringify(refs),key=refs[2].referenceKey
 assert.throws(()=>utils.selectCandidate(refs,{...video,assetVersionIds:['41']},'reference_video',null,[key]),/提示词/)
 const next=utils.selectCandidate(refs,{...video,assetVersionIds:['41']},'reference_video')
 assert.deepEqual(Array.from(next,x=>x.assetVersionId),['30','31','41'])
 assert.deepEqual(Array.from(next,x=>x.ordinal),[0,1,2])
 assert.notEqual(next[2].referenceKey,key)
 assert.equal(JSON.stringify(refs),before)
})
