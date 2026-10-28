const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
const tick = async () => { await vue.nextTick(); await new Promise(resolve => setImmediate(resolve)) }
function harness(deferCreate = false) {
  const exports = {}, hooks = {}, bindings = [], creates = [], normal = [], auth = vue.reactive({ token: 'one', user: { permissions: ['asset:create'] } })
  let changed = 0, keys = 0
  const api = {
    createUpload: (...args) => { creates.push(args); return deferCreate ? new Promise(resolve => { api.resolveCreate = resolve }) : Promise.resolve({ data: { id: '99' } }) },
    readUpload: async () => ({ data: { id: '99', state: 'ready' } }),
    bindAssetVersion: (...args) => new Promise((resolve, reject) => bindings.push({ args, resolve, reject })),
    bindAsset: (...args) => { normal.push(args); return Promise.resolve({ data: {} }) },
  }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useAssetUploads.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, AbortController, crypto: { randomUUID: () => String(++keys) }, require(name) {
      if (name === 'vue') return { ...vue, onBeforeUnmount(fn) { hooks.unmount=fn }, onDeactivated(fn) { hooks.deactivate=fn }, onActivated(fn) { hooks.activate=fn } }
      if (name.includes('stores/auth')) return { useAuthStore: () => auth }
      if (name.includes('utils/hash')) return { hashBlob: async () => 'sha' }
      if (name.includes('assetFormats')) return { assetUploadMime: file => file.type }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useAssetUploads('1', () => changed++))
  return { state, bindings, creates, normal, api, auth, hooks, changed: () => changed, close: () => { hooks.unmount(); scope.stop() } }
}
test('追加版本冻结目标和修订，绑定失败后重用上传与原幂等键', async () => {
  const h = harness(), asset = { id: '9007199254740993', revision: '7', mediaType: 'image', name: '素材' }
  h.state.enqueue([new File(['png'], 'new.png', { type: 'image/png' })], 'folder', asset)
  asset.revision = '8'; await tick()
  assert.equal(h.bindings[0].args[0], asset.id); assert.equal(h.bindings[0].args[1], '7')
  h.bindings[0].reject(new Error('响应丢失')); await tick()
  assert.equal(h.state.items[0].stage, 'failed')
  h.state.retry(h.state.items[0]); await tick()
  assert.equal(h.creates.length, 1); assert.equal(h.normal.length, 0)
  assert.equal(h.bindings[1].args[3], h.bindings[0].args[3]); assert.equal(h.bindings[1].args[2], '99')
  h.bindings[1].resolve({ data: {} }); await tick()
  assert.equal(h.state.items[0].stage, 'done'); assert.equal(h.changed(), 1)
  h.close()
})
test('跨类别在上传前拒绝，暂停后的迟到创建响应不会继续绑定', async () => {
  const h = harness(true), asset = { id: '1', revision: '1', mediaType: 'image', name: '素材' }
  h.state.enqueue([new File(['pdf'], 'doc.pdf', { type: 'application/pdf' })], null, asset); await tick()
  assert.equal(h.creates.length, 0); assert.match(h.state.items[0].error, /类别/)
  h.state.retry(h.state.items[0]); await tick(); assert.equal(h.creates.length, 0)
  h.state.enqueue([new File(['png'], 'new.png', { type: 'image/png' })], null, asset); await tick()
  h.state.pause(); h.api.resolveCreate({ data: { id: '99' } }); await tick()
  assert.equal(h.bindings.length, 0); assert.equal(h.state.items[1].stage, 'paused'); assert.equal(h.changed(), 0)
  h.close()
})

test('多文件失败只重试当前项，续传读取实时分片且不重传成功分片',async()=>{
 const h=harness(),parts=[],completed=[],bound=[];let fail=true,reads=0
 h.api.readUpload=async()=>({data:{id:'99',state:'uploading',partSize:'2',partCount:2,receivedParts:++reads===1?[1]:[1,2]}})
 h.api.putUploadPart=async(...args)=>{parts.push(args);if(fail){fail=false;throw Error('响应未知')}}
 h.api.completeUpload=async(...args)=>{completed.push(args);return {data:{}}}
 h.api.bindAsset=async(...args)=>{bound.push(args);return {data:{}}}
 const file=new File(['1234'],'a.png',{type:'image/png'})
 h.state.enqueue([file,file],null);await tick()
 assert.equal(h.state.items[0].stage,'failed');assert.equal(h.state.items[1].stage,'done')
 assert.equal(parts.length,1);assert.equal(parts[0][1],2)
 const successfulKey=bound[0][4],failed=h.state.items[0],createCount=h.creates.length
 h.state.retry(failed);await tick()
 assert.equal(h.creates.length,createCount);assert.equal(reads,3);assert.equal(parts.length,1)
 assert.equal(bound.length,2);assert.notEqual(bound[1][4],successfulKey);assert.equal(completed.length,2)
 assert.equal(h.state.items.every(item=>item.stage==='done'),true);h.close()
})

test('停用不自动续传，重新激活后明确继续，权限变化同步暂停',async()=>{
 const h=harness(true),file=new File(['png'],'a.png',{type:'image/png'})
 h.state.enqueue([file,file],null);await tick();h.hooks.deactivate()
 assert.equal(h.creates[0][4].aborted,true);h.api.resolveCreate({data:{id:'99'}});await tick()
 const item=h.state.items[0];h.state.retry(item);h.state.enqueue([file],null);await tick();assert.equal(h.creates.length,1);assert.equal(h.state.items.length,2)
 h.hooks.activate();await tick();assert.equal(h.normal.length,0)
 h.state.retry(item);await tick();assert.equal(h.normal.length,1)
 h.state.retry(h.state.items[1]);await tick();h.auth.user.permissions=[]
 assert.equal(h.creates[1][4].aborted,true);h.api.resolveCreate({data:{id:'100'}});await tick()
 assert.equal(h.normal.length,1);assert.equal(h.state.items[1].stage,'paused');h.close()
})

test('账号切换同步清队列，旧项不能重新排队，卸载后禁止新增',async()=>{
 const h=harness(true),file=new File(['png'],'a.png',{type:'image/png'})
 h.state.enqueue([file],null);await tick();const old=h.state.items[0]
 h.auth.token='two';assert.equal(h.state.items.length,0);assert.equal(h.creates[0][4].aborted,true)
 h.api.resolveCreate({data:{id:'99'}});await tick();h.state.retry(old);await tick();assert.equal(h.creates.length,1)
 h.close();h.state.enqueue([file],null);await tick();assert.equal(h.state.items.length,0);assert.equal(h.changed(),0)
})
