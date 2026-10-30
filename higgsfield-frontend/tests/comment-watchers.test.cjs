const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const settle = async () => { for (let n=0;n<5;n++) { await Promise.resolve(); await vue.nextTick() } }
for (const name of ['useCommentOverview','useCommentCollaboration']) {
  test(`${name}：同值目标重建不会重复请求，切换素材或登录状态仍重新加载`, async () => {
    const target=vue.ref({assetVersionId:'13'}), auth=vue.reactive({token:'valid',user:{permissions:['comment:read']}})
    const exports={}, calls=[]
    const code=ts.transpileModule(readFileSync(`src/composables/${name}.ts`,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
    runInNewContext(code,{exports,AbortController,Date,Error,Map,crypto:globalThis.crypto,require(id){
      if(id==='vue') return {...vue,onBeforeUnmount(){}}
      if(id==='@/stores/auth') return {useAuthStore:()=>auth}
      if(id==='@/api/projectWorkspace') return {readMembers:async()=>{calls.push('members');return {total:0,rows:[]}}}
      return {listCommentThreads:async()=>{calls.push('threads');return {total:0,rows:[]}},listComments:async()=>({total:0,rows:[]})}
    }})
    const scope=vue.effectScope()
    try {
      scope.run(()=> name==='useCommentOverview'
        ? exports[name](()=>target.value,()=>true)
        : exports[name](()=> '2',()=>JSON.stringify(target.value),async()=>{},async()=>{}))
      await settle()
      assert.equal(calls.length,1)
      for(let n=0;n<20;n++) { target.value={assetVersionId:'13'}; await settle() }
      assert.equal(calls.length,1,'同一视频的播放更新与父组件重绘不得重新加载')
      target.value={assetVersionId:'14'}; await settle()
      assert.equal(calls.length,2)
      auth.token='renewed'; await settle()
      assert.equal(calls.length,3)
    } finally { scope.stop() }
  })
}
