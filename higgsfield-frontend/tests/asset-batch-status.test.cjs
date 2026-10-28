const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function setup(options) {
  const exports = {}, calls = [], hooks = {}, auth = vue.reactive({ token: 'one' })
  let confirmations = 0, serial = 0, fail = false
  class ApiError extends Error {}
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useBatchAction.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText, {
    exports, Error, crypto: { randomUUID: () => String(++serial) },
    require(id) {
      if(id === 'vue') return {...vue,onActivated:fn=>hooks.activate=fn,onDeactivated:fn=>hooks.deactivate=fn,onBeforeUnmount:fn=>hooks.close=fn}
      if(id === 'vue-router') return {onBeforeRouteLeave(){},onBeforeRouteUpdate(){}}
      if(id === 'element-plus') return {ElMessageBox:{confirm:async()=>confirmations++}}
      if(id.includes('stores/auth')) return {useAuthStore:()=>auth}
      return {ApiError}
    }
  })
  const rows=vue.ref([{id:'1',name:'甲',revision:'1',targetStatus:'working'}]), selected=vue.ref(['1']), scope=vue.effectScope()
  const state=scope.run(()=>exports.useBatchAction(()=>rows.value,()=>true,async()=>{},async(item,key)=>{calls.push({item:{...item},key});if(fail)throw new Error('断网')},()=>true,'素材','更新状态','',selected,options))
  return {state,rows,selected,calls,confirmations:()=>confirmations,setFail:v=>fail=v,close(){hooks.close();scope.stop()}}
}
test('状态更新不重复确认且保留素材选择',async()=>{
  const h=setup({confirm:false,preserveSelection:true});await h.state.execute()
  assert.equal(h.confirmations(),0);assert.deepEqual([...h.selected.value],['1']);assert.equal(h.calls.length,1);h.close()
})
test('网络异常重试沿用原状态、修订和幂等键',async()=>{
  const h=setup({confirm:false,preserveSelection:true});h.setFail(true);await h.state.execute()
  h.rows.value[0].targetStatus='approved';h.rows.value[0].revision='2';h.setFail(false);await h.state.execute()
  assert.equal(h.calls[1].key,h.calls[0].key);assert.equal(h.calls[1].item.targetStatus,'working');assert.equal(h.calls[1].item.revision,'1');h.close()
})
test('原有删除等批量操作仍需确认并移除成功选择',async()=>{
  const h=setup();await h.state.execute();assert.equal(h.confirmations(),1);assert.equal(h.selected.value.length,0);h.close()
})
