const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code) { super(message); this.code = code } }
const recovery = {}
runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/utils/outputAssetRecovery.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: recovery, structuredClone })
test.beforeEach(() => recovery.clearOutputAssetRecovery())
async function setup(overrides = {}) {
  const exports = {}, hooks = {}, calls = [], auth = vue.reactive({ token: 'one', user: { permissions: ['asset:create'] } })
  const api = { ApiError,
    getProjects: async () => ({ rows: [], total: 0 }),
    readBrief: async () => ({ data: { allowedActions: ['asset:create'] } }),
    listFolders: async () => ({ rows: [], total: 0 }),
    outputToAsset: async (...args) => { calls.push(args); return { data: { id: '9007199254740995', name: '素材' } } },
    ...overrides,
  }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useOutputToAsset.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, crypto: { randomUUID }, require(id) {
      if (id === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn }, onDeactivated: fn => { hooks.deactivate = fn } }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/utils/outputAssetRecovery') return recovery
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useOutputToAsset('9007199254740993', '12'))
  state.form.value = { validate: async () => true }
  await new Promise(resolve => setImmediate(resolve))
  return { state, calls, hooks, auth, close: () => { hooks.unmount(); scope.stop() } }
}
test('入库保留字符串ID和目录，成功后禁止重复提交', async () => {
  const c = await setup(); c.state.enter({ id: '77', name: '子目录' }); c.state.fields.name = '新素材'
  await c.state.submit(); await c.state.submit()
  assert.equal(c.calls.length, 1); assert.equal(c.calls[0][0], '9007199254740993')
  assert.equal(c.calls[0][1].folderId, '77'); assert.equal(c.state.result.value.id, '9007199254740995'); c.close()
})
test('网络结果不明锁定意图，原键重试，确定业务错误允许修改', async () => {
  const calls = []
  const c = await setup({ outputToAsset: async (...args) => { calls.push(args); if (calls.length === 1) throw new ApiError('断网', 0); return { data: { id: '7' } } } })
  await c.state.submit(); assert.equal(c.state.locked.value, true); assert.equal(c.hooks.leave(), false)
  c.state.enter({ id: '99' }); assert.equal(c.state.fields.folderId, null)
  await c.state.submit(); assert.equal(calls[0][2], calls[1][2]); assert.equal(c.state.locked.value, false); c.close()
  const rejected = await setup({ outputToAsset: async () => { throw new ApiError('目录已移除', 601) } })
  await rejected.state.submit(); assert.equal(rejected.state.uncertain.value, false); rejected.close()
})
test('切换账号时旧提交不能回填成功，清理项目及目录', async () => {
  let resolve, signal
  const c = await setup({ outputToAsset: (...args) => { signal = args[3]; return new Promise(done => { resolve = done }) } })
  const pending = c.state.submit(); await new Promise(done => setImmediate(done)); c.auth.token = 'two'
  resolve({ data: { id: 'private' } }); await pending
  assert.equal(signal.aborted, true); assert.equal(c.state.result.value, undefined)
  assert.equal(c.state.fields.projectId, ''); assert.equal(c.state.fields.name, ''); c.close()
})
test('无目标创建权限禁止提交，换项目后丢弃旧目录响应', async () => {
  const denied = await setup({ readBrief: async () => ({ data: { allowedActions: [] } }) })
  await denied.state.submit(); assert.equal(denied.calls.length, 0); denied.close()
  const resolvers = []
  const c = await setup({ listFolders: () => new Promise(done => { resolvers.push(done) }) })
  c.state.fields.projectId = '13'; await vue.nextTick(); await vue.nextTick()
  resolvers[0]({ rows: [{ id: 'old' }], total: 1 }); await vue.nextTick()
  assert.equal(c.state.folders.value.length, 0)
  resolvers[1]({ rows: [{ id: 'new' }], total: 1 }); await new Promise(done => setImmediate(done))
  assert.equal(c.state.folders.value[0].id, 'new'); c.close()
})

test('入库超时或幂等处理中保持原目录和键，禁止切目录后另建意图',async()=>{
 for(const code of [408,601]){
  const attempts=[]
  const c=await setup({outputToAsset:async(...args)=>{
   attempts.push(args)
   if(attempts.length===1){const error=new ApiError('等待确认',code);if(code===601)error.errorCode='IDEMPOTENCY_IN_PROGRESS';throw error}
   return {data:{id:'confirmed'}}
  }})
  c.state.enter({id:'9007199254740993',name:'原目录'})
  await c.state.submit();assert.equal(c.state.uncertain.value,true)
  assert.equal(c.hooks.leave(),false);c.state.enter({id:'other'})
  assert.equal(c.state.fields.folderId,'9007199254740993')
  await c.state.submit();assert.equal(attempts[1][2],attempts[0][2])
  assert.equal(attempts[1][1].folderId,'9007199254740993')
  assert.equal(c.state.result.value.id,'confirmed');assert.equal(c.state.locked.value,false);c.close()
 }
})

test('入库校验不提交后来修改的名称或目录，重新校验后使用当前内容',async()=>{
 for(const change of [s=>{s.fields.name='改名'},s=>s.enter({id:'77',name:'改目录'})]){
  const c=await setup();let validate
  c.state.form.value={validate:()=>new Promise(resolve=>{validate=resolve})}
  const submit=c.state.submit();change(c.state);validate(true);await submit
  assert.equal(c.calls.length,0)
  c.state.form.value={validate:async()=>true};await c.state.submit()
  assert.equal(c.calls.length,1);assert.equal(c.calls[0][1].name,c.state.fields.name)
  assert.equal(c.calls[0][1].folderId,c.state.fields.folderId);c.close()
 }
})

test('目标项目离开再返回仍使旧入库校验失效',async()=>{
 const c=await setup();let validate
 c.state.form.value={validate:()=>new Promise(resolve=>{validate=resolve})}
 const submit=c.state.submit()
 c.state.fields.projectId='13';await new Promise(resolve=>setImmediate(resolve))
 c.state.fields.projectId='12';await new Promise(resolve=>setImmediate(resolve))
 validate(true);await submit;assert.equal(c.calls.length,0);c.close()
})

test('权限复核使旧表单校验失效，不沿用旧目标授权提交',async()=>{
 let allow=true,validate
 const c=await setup({readBrief:async()=>({data:{allowedActions:allow?['asset:create']:[]}})})
 c.state.form.value={validate:()=>new Promise(resolve=>validate=resolve)}
 const pending=c.state.submit();allow=false;c.auth.user.permissions=[];validate(true);await pending
 await new Promise(resolve=>setImmediate(resolve));assert.equal(c.calls.length,0);assert.equal(c.state.allowed.value,false);c.close()
})

test('未知入库撤权后恢复保留原目录、名称和幂等键',async()=>{
 let allow=true;const calls=[]
 const c=await setup({readBrief:async()=>({data:{allowedActions:allow?['asset:create']:[]}}),outputToAsset:async(...args)=>{
 calls.push(args);if(calls.length===1)throw new ApiError('断网',0);return {data:{id:'confirmed'}}
 }})
 c.state.enter({id:'77',name:'原目录'});c.state.fields.name='原名称';await c.state.submit()
 allow=false;c.auth.user.permissions=[];await new Promise(resolve=>setImmediate(resolve));await c.state.submit()
 assert.equal(calls.length,1);assert.equal(c.state.fields.folderId,'77');assert.equal(c.state.uncertain.value,true)
 allow=true;c.auth.user.permissions=['asset:create'];await new Promise(resolve=>setImmediate(resolve));await c.state.submit()
 assert.equal(calls.length,2);assert.equal(calls[0][2],calls[1][2]);assert.equal(calls[1][1].folderId,'77');assert.equal(calls[1][1].name,'原名称');c.close()
})

test('缓存停用后权限变化和显式加载不读取，恢复只按当前身份查询',async()=>{
 let projectReads=0,briefReads=0,folderReads=0
 const c=await setup({getProjects:async()=>{projectReads++;return {rows:[],total:0}},readBrief:async()=>{briefReads++;return {data:{allowedActions:['asset:create']}}},listFolders:async()=>{folderReads++;return {rows:[],total:0}}})
 c.hooks.deactivate();const before=[projectReads,briefReads,folderReads];c.auth.user.permissions=[];c.state.filter();await c.state.loadFolders();await new Promise(resolve=>setImmediate(resolve))
 assert.deepEqual([projectReads,briefReads,folderReads],before);assert.equal(c.state.allowed.value,false)
 c.hooks.activate();await new Promise(resolve=>setImmediate(resolve));assert.equal(projectReads,before[0]+1);assert.equal(briefReads,before[1]);c.close()
})

test('未知结果撤权可退出，重开同一作品恢复原目标和键',async()=>{
 const attempts=[];let allow=true
 const api={readBrief:async()=>({data:{allowedActions:allow?['asset:create']:[]}}),outputToAsset:async(...args)=>{
 attempts.push(args);if(attempts.length===1)throw new ApiError('断网',0);return {data:{id:'confirmed'}}
 }}
 const first=await setup(api);first.state.enter({id:'77',name:'原目录'});first.state.fields.name='原名称';await first.state.submit()
 allow=false;first.auth.user.permissions=[];await new Promise(resolve=>setImmediate(resolve))
 assert.equal(first.state.canClose.value,true);assert.equal(first.hooks.leave(),true);first.close()
 const second=await setup(api);assert.equal(second.state.uncertain.value,true);assert.equal(second.state.fields.folderId,'77');assert.equal(second.state.fields.name,'原名称')
 allow=true;second.auth.user.permissions=['asset:create','extra'];await new Promise(resolve=>setImmediate(resolve));await second.state.submit()
 assert.equal(attempts[0][2],attempts[1][2]);assert.equal(attempts[1][1].folderId,'77');second.close()
 const third=await setup(api);assert.equal(third.state.uncertain.value,false);third.close()
})

test('同作品另一面板不能覆盖未确认意图，退出登录清除恢复数据',async()=>{
 const calls=[];const api={outputToAsset:async(...args)=>{calls.push(args);throw new ApiError('断网',0)}}
 const first=await setup(api),second=await setup(api)
 first.state.fields.name='第一次';await first.state.submit();second.state.fields.name='另一次';await second.state.submit()
 assert.equal(calls.length,1);assert.equal(second.state.fields.name,'第一次');assert.equal(second.state.uncertain.value,true)
 second.auth.token='two';assert.equal(recovery.readOutputAssetRecovery('two','9007199254740993'),undefined)
 first.close();second.close()
})

test('写入中卸载后原请求可恢复，迟到成功清除该请求恢复记录',async()=>{
 let finish;const first=await setup({outputToAsset:()=>new Promise(resolve=>finish=resolve)})
 const pending=first.state.submit();await new Promise(resolve=>setImmediate(resolve));first.close()
 const second=await setup();assert.equal(second.state.uncertain.value,true);second.close()
 finish({data:{id:'done'}});await pending
 const third=await setup();assert.equal(third.state.uncertain.value,false);third.close()
})
