const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = () => new Promise(resolve => setImmediate(resolve))
function setup(readAsset, readAssetVersion = readAsset) {
 const route = vue.reactive({ params: {id:'2'}, query: {tab:'folders',folder:'5',asset:'7'} })
 const opened=[], errors=[], calls=[]
 const exports={}, scope=vue.effectScope()
 const code=ts.transpileModule(readFileSync('src/composables/useAssetPreviewRoute.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
 runInNewContext(code,{exports,AbortController,Error,require(id){
  if(id==='vue') return {...vue,onBeforeUnmount(){}}
  if(id==='vue-router') return {useRoute:()=>route,useRouter:()=>({push:async value=>{calls.push(value);route.query=value.query}})}
  if(id==='@/api/assets') return {readAsset,readAssetVersion}
  return {useAuthStore:()=>({token:'valid',user:{permissions:['asset:read']}})}
 }})
 const api=scope.run(()=>exports.useAssetPreviewRoute('2',()=>true,async asset=>opened.push(asset.id),()=>{},message=>errors.push(message),()=> '5'))
 return {route,opened,errors,calls,api,scope}
}
test('直接链接恢复预览，打开与关闭保留目录，后退地址恢复素材',async()=>{
 const c=setup(async id=>({data:{id}}));await tick();assert.deepEqual(c.opened,['7'])
 await c.api.openPreview({id:'8'});await tick();assert.equal(c.route.query.folder,'5');assert.equal(c.opened.at(-1),'8')
 c.api.closePreview();await tick();assert.equal(c.route.query.asset,undefined);assert.equal(c.route.query.folder,'5')
 c.route.query.asset='7';await tick();assert.equal(c.opened.at(-1),'7');c.scope.stop()
})
test('快速切换忽略旧请求，无权限只显示错误不打开素材',async()=>{
 let finish
 const c=setup(id=>id==='7'?new Promise(resolve=>finish=resolve):Promise.reject(new Error('无权访问')))
 c.route.query.asset='8';await tick();finish({data:{id:'7'}});await tick()
 assert.deepEqual(c.opened,[]);assert.deepEqual(c.errors,['无权访问']);c.scope.stop()
})


test('元素缩略图打开固定版本，关闭后返回元素库',async()=>{
 const versions=[]
 const c=setup(async id=>({data:{id}}),async id=>{versions.push(id);return {data:{id:'42',currentVersionId:id}}})
 await tick()
 c.route.query={tab:'folders',folder:'5',assetVersion:'13',previewFrom:'elements'}
 await tick()
 assert.deepEqual(versions,['13'])
 assert.equal(c.opened.at(-1),'42')
 await c.api.closePreview();await tick()
 assert.equal(c.route.query.tab,'elements')
 assert.equal(c.route.query.assetVersion,undefined)
 assert.equal(c.route.query.folder,'5')
 c.scope.stop()
})
