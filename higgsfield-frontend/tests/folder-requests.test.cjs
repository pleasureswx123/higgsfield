const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code=code; this.errorCode=errorCode } }
function harness(initialVisible = true) {
  const route=vue.reactive({query:{}}), visible=vue.ref(initialVisible)
  const exports = {}, auth = vue.reactive({ token: 'one' }), calls = [], actions = [], confirmations = [], reads = []
  let unmount, activate, deactivate, mount, keys = 0
  const api = { listFolders: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
    readFolder: (...args) => new Promise((resolve, reject) => reads.push({ args, resolve, reject })),
    actOnFolder: (...args) => { actions.push(args); return Promise.resolve({ data: {} }) } }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useFolders.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, Error, AbortController, crypto: { randomUUID: () => `test-key-${++keys}` },
    require(name) {
      if (name === 'vue') return { ...vue, onMounted: fn => {mount=fn}, onActivated: fn => { activate=fn }, onDeactivated: fn => { deactivate=fn }, onBeforeUnmount: fn => { unmount = fn } }
      if (name === 'vue-router') return { onBeforeRouteLeave(){}, onBeforeRouteUpdate(){}, useRoute: () => route, useRouter: () => ({ push() {} }) }
      if (name === 'element-plus') return { ElMessageBox: { confirm: () => new Promise(resolve => confirmations.push(resolve)) } }
      if (name==='@/api/client') return {ApiError}
      if (name.includes('stores/auth')) return { useAuthStore: () => auth }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useFolders('9007199254740993',()=>visible.value))
  return { state, api, calls, actions, confirmations, reads, auth, route, visible, mount:()=>mount(), activate:()=>activate(), deactivate:()=>deactivate(), close() { unmount(); scope.stop() } }
}
test('节点刷新拒绝迟到结果，加载更多去重且保留字符串ID', async () => {
  const h = harness(), old = h.state.loadTree(), fresh = h.state.loadTree()
  assert.equal(h.calls[0].args[2].aborted, true)
  h.calls[1].resolve({ rows: [{ id: '9007199254740993' }], hasNext: true }); await fresh
  h.calls[0].resolve({ rows: [{ id: 'old' }], hasNext: false }); await old
  assert.equal(h.state.roots.value[0].id, '9007199254740993')
  const more = h.state.loadTree(null, true); await h.state.loadTree(null, true)
  assert.equal(h.calls.length, 3); assert.equal(h.calls[2].args[1].pageNum, 2)
  h.calls[2].resolve({ rows: [{ id: '9007199254740993', name: '最新' }, { id: '2' }], hasNext: false }); await more
  assert.equal(h.state.roots.value.length, 2); assert.equal(h.state.roots.value[0].name, '最新')
  await h.state.loadTree(null, true); assert.equal(h.calls.length, 3)
  h.close()
})

test('目标内新建校验后保留父路径，失败重试同一键且不自动移动源目录', async () => {
  const h = harness(), created = [], parent = { id: '20', name: '目标父目录', folderKind: 'media' }
  h.api.listFolders = async () => ({ rows: [], total: 0, hasNext: false })
  h.state.startDestination({ id: '7', revision: '1', folderKind: 'media' }, 'copy')
  await new Promise(setImmediate)
  h.state.chooseDestination([parent]); await new Promise(setImmediate)
  h.state.startDestinationCreate()
  assert.equal(h.state.createInDestination.value, true)
  h.state.fields.name = ' 新目标 '
  h.state.form.value = { validate: async () => false }
  h.api.createFolder = async (...args) => {
    created.push(args)
    if (created.length === 1) throw new Error('连接中断')
    return { data: { id: '30', name: '新目标', parentId: '20', folderKind: 'media' } }
  }
  await h.state.save(); assert.equal(created.length, 0)
  h.state.form.value = { validate: async () => true }
  await h.state.save()
  assert.equal(h.state.dialog.value, true); assert.equal(h.state.fields.name, ' 新目标 ')
  assert.equal(h.state.destinationCrumbs.value.at(-1).id, '20')
  await h.state.save()
  assert.equal(created[0][1].parentId, '20'); assert.equal(created[0][1].name, '新目标')
  assert.equal(created[0][2], created[1][2]); assert.equal(h.actions.length, 0)
  assert.equal(h.state.dialog.value, false); assert.equal(h.state.destinationOpen.value, true)
  assert.equal(h.state.destinationCrumbs.value[0].id, '20'); assert.equal(h.state.destinationCrumbs.value[1].id, '30')
  h.close()
})

test('目标搜索排序分页重置，选中平铺结果恢复真实祖先并拒绝源子树', async () => {
  const h = harness(), source = { id: '7', revision: '1', folderKind: 'media' }
  h.state.startDestination(source, 'move')
  h.calls[0].resolve({ rows: [], hasNext: false }); await new Promise(setImmediate)
  h.state.destinationSearch.value = '目标'; h.state.destinationSort.value = 'updatedDesc'
  const search = h.state.loadDestinations()
  assert.equal(h.calls[1].args[1].q, '目标'); assert.equal(h.calls[1].args[1].sort, 'updatedDesc')
  h.calls[1].resolve({ rows: [{ id: '7' }, { id: '8' }], hasNext: true }); await search
  assert.equal(h.state.destinations.value.length, 1)
  await h.state.transfer(); assert.equal(h.actions.length, 0)
  h.state.destinationSearch.value = '新目标'
  const changedQuery = h.state.loadDestinations(true)
  assert.equal(h.calls[2].args[1].pageNum, 1)
  h.calls[2].resolve({ rows: [{ id: '8' }], hasNext: false }); await changedQuery
  const invalid = h.state.enterDestination({ id: '8' })
  h.reads[0].resolve({ data: { ancestors: [{ id: '7' }], folder: { id: '8' } } }); await invalid
  assert.match(h.state.dialogError.value, /子目录/)
  const valid = h.state.enterDestination({ id: '8' })
  h.reads[1].resolve({ data: { ancestors: [{ id: '2', name: '其他分支' }], folder: { id: '8', projectId: '9007199254740993', folderKind: 'media' } } }); await valid
  assert.equal(h.state.destinationCrumbs.value[0].id, '2')
  assert.equal(h.state.destinationSearch.value, '')
  assert.equal(h.calls[3].args[1].parentId, '8')
  h.calls[3].resolve({ rows: [], hasNext: false }); await new Promise(setImmediate)
  assert.equal(h.state.destinationLoading.value, false)
  h.close()
})
test('退出清理树且取消请求，确认对话框跨账号后不发送删除', async () => {
  const h = harness(), loading = h.state.loadTree('1')
  h.state.expanded.add('1'); h.state.roots.value = [{ id: '1' }]
  const deleting = h.state.remove({ id: '1', name: '目录', revision: '1' })
  h.auth.token = ''
  assert.equal(h.calls[0].args[2].aborted, true)
  h.calls[0].resolve({ rows: [{ id: 'old' }], hasNext: false }); await loading
  h.confirmations[0](); await deleting
  assert.equal(h.actions.length, 0); assert.equal(h.state.roots.value.length, 0)
  assert.equal(h.state.children['1'], undefined); assert.equal(h.state.expanded.size, 0)
  h.close()
})


test('目录删除确认锁定重复点击，外部对象变化不改变确认时修订', async () => {
 const h=harness(), folder={id:'7',name:'原目录',revision:'1'}
 h.api.listFolders=async()=>({rows:[],total:0,hasNext:false})
 const first=h.state.remove(folder); assert.equal(h.state.pending.value,true)
 await h.state.remove(folder); assert.equal(h.confirmations.length,1)
 h.state.startCreate(null); assert.equal(h.state.dialog.value,false)
 folder.revision='9'; folder.id='other'; h.confirmations[0](); await first
 assert.equal(h.actions[0][0],'7'); assert.equal(h.actions[0][2].revision,'1'); assert.equal(h.state.pending.value,false); h.close()
})

test('目录编辑独立快照，校验期间改字段或关闭不能发起保存', async () => {
 const h=harness(), folder={id:'7',name:'原目录',revision:'1',description:'',color:'lime'}
 let resolve, writes=0
 h.api.updateFolder=async()=>{writes++; return {data:folder}}
 h.state.startEdit(folder); folder.revision='9'; assert.equal(h.state.editing.value.revision,'1')
 h.state.form.value={validate:()=>new Promise(done=>{resolve=done})}
 const first=h.state.save(); h.state.fields.name='新输入'; resolve(true); await first; assert.equal(writes,0)
 const second=h.state.save(); h.state.dialog.value=false; resolve(true); await second; assert.equal(writes,0); h.close()
})


test('目录创建未知结果固定原父级字段与键，确认后解除锁定', async () => {
 const h=harness(), writes=[]
 h.api.listFolders=async()=>({rows:[],total:0,hasNext:false})
 h.api.createFolder=async(...args)=>{writes.push(args); if(writes.length===1)throw new Error('中断'); return {data:{id:'new',name:'原目录'}}}
 h.state.startCreate('parent'); h.state.fields.name='原目录'; h.state.form.value={validate:async()=>true}
 await h.state.save(); assert.equal(h.state.saveUncertain.value,true)
 h.state.startCreate('other'); h.state.startEdit({id:'other',revision:'9',name:'其他'})
 h.state.fields.name='意外修改'; await h.state.save()
 assert.equal(writes[1][1].name,'原目录'); assert.equal(writes[1][1].parentId,'parent'); assert.equal(writes[0][2],writes[1][2])
 assert.equal(h.state.saveLocked.value,false); assert.equal(h.state.dialog.value,false); h.close()
})

test('目录编辑明确拒绝解锁，账号切换隔离未知写入的迟到成功', async () => {
 const h=harness(); h.api.listFolders=async()=>({rows:[],total:0,hasNext:false})
 h.api.updateFolder=async()=>{throw new ApiError('冲突',601,'REVISION_CONFLICT')}
 h.state.startEdit({id:'7',revision:'1',name:'旧名',description:'',color:'lime'}); h.state.fields.name='保留'; h.state.form.value={validate:async()=>true}
 await h.state.save(); assert.equal(h.state.saveLocked.value,false); assert.equal(h.state.fields.name,'保留')
 let resolve; h.api.updateFolder=()=>new Promise(done=>{resolve=done})
 const pending=h.state.save(); await new Promise(setImmediate); h.auth.token='two'; resolve({data:{id:'private',name:'旧账号'}}); await pending
 assert.equal(h.state.saveUncertain.value,false); assert.equal(h.state.dialog.value,false); h.close()
})

test('目录移动复制未知结果固定源修订方向目标及键，成功后不重复提交', async () => {
 for(const mode of ['move','copy']) {
  const h=harness(), writes=[]
  h.api.listFolders=async()=>({rows:[],total:0,hasNext:false})
  h.api.actOnFolder=async(...args)=>{writes.push(args); if(writes.length===1)throw new Error('中断'); return {data:{}}}
  h.state.startDestination({id:'7',revision:'1',folderKind:'media'},mode); await new Promise(setImmediate)
  h.state.chooseDestination([{id:'target'}]); await new Promise(setImmediate); await h.state.transfer()
  assert.equal(h.state.transferUncertain.value,true)
  h.state.chooseDestination([{id:'other'}]); h.state.startDestination({id:'other',revision:'9'},'copy')
  h.state.destinationMode.value=mode==='move'?'copy':'move'; await h.state.transfer()
  assert.equal(writes[1][0],'7'); assert.equal(writes[1][1],mode); assert.equal(writes[1][2].revision,'1')
  assert.equal(writes[1][2][mode==='move'?'parentId':'targetParentId'],'target'); assert.equal(writes[0][3],writes[1][3])
  assert.equal(h.state.transferUncertain.value,false); assert.equal(h.state.destinationOpen.value,false); await h.state.transfer(); assert.equal(writes.length,2); h.close()
 }
})

test('目录复制明确拒绝保留目标可修正，账号变化清除未知意图', async () => {
 const h=harness(); h.api.listFolders=async()=>({rows:[],total:0,hasNext:false})
 h.api.actOnFolder=async()=>{throw new ApiError('目标失效',601,'TARGET_NOT_FOUND')}
 h.state.startDestination({id:'7',revision:'1',folderKind:'media'},'copy'); await new Promise(setImmediate)
 await h.state.transfer(); assert.equal(h.state.transferUncertain.value,false); assert.equal(h.state.destinationOpen.value,true)
 h.api.actOnFolder=async()=>{throw new Error('中断')}; await h.state.transfer(); assert.equal(h.state.transferUncertain.value,true)
 h.auth.token='two'; assert.equal(h.state.transferUncertain.value,false); assert.equal(h.state.destinationOpen.value,false); h.close()
})



test('权限变化清除目录草稿和目标路径，旧刷新链不再读取子树', async () => {
 const h=harness(); h.auth.user={user:{userId:'1'},permissions:['folder:write']}
 await new Promise(setImmediate)
 // 清理本次身份初始化读请求，后续只核对明确发起的刷新链。
 for(const call of h.calls) call.resolve({rows:[],total:0,hasNext:false})
 await new Promise(setImmediate)
 h.state.startCreate('private-parent'); h.state.fields.name='私密名称'; h.state.fields.description='私密描述'
 h.state.destinationCrumbs.value=[{id:'private',name:'私密目录'}]; h.state.destinationSearch.value='私密搜索'
 h.state.expanded.add('old-child')
 const refresh=h.state.refresh(), old=h.calls.at(-1)
 h.auth.user.permissions=[]; await new Promise(setImmediate)
 const after=h.calls.length
 old.resolve({rows:[{id:'old'}],total:1,hasNext:false}); await refresh
 assert.equal(h.calls.length,after); assert.equal(h.state.fields.name,''); assert.equal(h.state.fields.description,'')
 assert.equal(h.state.destinationCrumbs.value.length,0); assert.equal(h.state.destinationSearch.value,''); assert.equal(h.state.dialog.value,false)
 h.auth.token=''; const count=h.calls.length; await h.state.loadTree(); await h.state.refresh(); assert.equal(h.calls.length,count)
 h.close()
})

test('目录写请求遇权限变化后不恢复旧表单或未知意图', async () => {
 const h=harness(); h.auth.user={user:{userId:'1'},permissions:['folder:write']}
 h.api.listFolders=async()=>({rows:[],total:0,hasNext:false}); await new Promise(setImmediate)
 let resolve; h.api.createFolder=()=>new Promise(done=>{resolve=done})
 h.state.startCreate(null); h.state.fields.name='旧内容'; h.state.form.value={validate:async()=>true}
 const saving=h.state.save(); await new Promise(setImmediate)
 h.auth.user.permissions=[]; resolve({data:{id:'old',name:'旧内容'}}); await saving
 assert.equal(h.state.dialog.value,false); assert.equal(h.state.fields.name,''); assert.equal(h.state.saveUncertain.value,false); h.close()
})

test('目录关闭确认保留当前表单，旧确认不能关闭重新打开的编辑', async () => {
 const h=harness(); h.state.startCreate(null); h.state.fields.name='未保存'; h.state.fields.description='描述'; h.state.fields.color='pink'
 const closing=h.state.closeEditor(); assert.equal(h.confirmations.length,1); assert.equal(h.state.dialog.value,true)
 h.state.startEdit({id:'new',revision:'1',name:'新的表单',description:'',color:'lime'})
 h.confirmations[0](); await closing; assert.equal(h.state.dialog.value,true); assert.equal(h.state.fields.name,'新的表单')
 h.state.fields.name='修改后的表单'; const confirmed=h.state.closeEditor(); h.confirmations[1](); await confirmed
 assert.equal(h.state.dialog.value,false); h.close()
})

test('目录关闭后以相同内容重开，旧校验不能提交新表单', async () => {
 const h=harness(); let resolve,writes=0
 h.api.createFolder=async()=>{writes++; return {data:{}}}
 h.state.startCreate(null); h.state.form.value={validate:()=>new Promise(done=>{resolve=done})}
 const saving=h.state.save(); await h.state.closeEditor(); h.state.startCreate(null); resolve(true); await saving
 assert.equal(writes,0); assert.equal(h.state.dialog.value,true); h.close()
})


test('目录页缓存隐藏停止读取与旧确认，返回后保留表单并重读', async () => {
 const h=harness(); h.api.listFolders=async(...args)=>{h.calls.push({args}); return {rows:[],total:0,hasNext:false}}
 h.state.startCreate(null); h.state.fields.name='保留草稿'
 const closing=h.state.closeEditor(); h.deactivate(); const count=h.calls.length
 await h.state.refresh(); await h.state.loadTree(); await h.state.loadDestinations(); h.state.startCreate('other')
 assert.equal(h.calls.length,count); assert.equal(h.state.fields.name,'保留草稿')
 h.activate(); h.confirmations[0](); await closing; await new Promise(setImmediate)
 assert.equal(h.state.dialog.value,true); assert.equal(h.state.fields.name,'保留草稿'); assert.ok(h.calls.length>count); h.close()
})

test('缓存隐藏使目录校验失效，但已发出写入可确认且不在后台刷新', async () => {
 const h=harness(); h.api.listFolders=async(...args)=>{h.calls.push({args});return {rows:[],total:0,hasNext:false}}
 let resolve,writes=0; h.api.createFolder=()=>{writes++;return new Promise(done=>{resolve=done})}
 h.state.startCreate(null); h.state.fields.name='目录'
 let validate; h.state.form.value={validate:()=>new Promise(done=>{validate=done})}
 const first=h.state.save(); h.deactivate(); h.activate(); validate(true); await first; assert.equal(writes,0)
 h.state.form.value={validate:async()=>true}; const second=h.state.save(); await new Promise(setImmediate)
 h.deactivate(); const count=h.calls.length; resolve({data:{id:'new',name:'目录'}}); await second
 assert.equal(h.calls.length,count); assert.equal(h.state.saveUncertain.value,false); assert.equal(h.state.dialog.value,false)
 h.activate(); await new Promise(setImmediate); assert.ok(h.calls.length>count); h.close()
})


test('同目录缓存恢复保留搜索排序和分页，隐藏期间切目录则重置筛选', async () => {
 const h=harness(), queries=[]
 h.api.listFolders=async(_project,params)=>{queries.push({...params}); return {rows:[],total:90,hasNext:false}}
 h.mount(); await new Promise(setImmediate)
 h.state.search.value='镜头'; h.state.sort.value='updatedDesc'; h.state.page.value=3
 h.deactivate(); h.activate(); await new Promise(setImmediate)
 assert.equal(h.state.search.value,'镜头'); assert.equal(h.state.page.value,3); assert.equal(h.state.sort.value,'updatedDesc')
 assert.ok(queries.some(query=>query.q==='镜头'&&query.pageNum===3&&query.sort==='updatedDesc'))
 h.deactivate(); h.route.query.folder='different'; await new Promise(setImmediate); h.activate()
 h.reads.at(-1).resolve({data:{ancestors:[],folder:{id:'different',projectId:'9007199254740993',name:'另一目录'}}}); await new Promise(setImmediate)
 assert.equal(h.state.search.value,''); assert.equal(h.state.page.value,1); assert.equal(h.state.currentId.value,'different'); h.close()
})


test('目录页签初始隐藏不读取，v-show显隐保留筛选且与KeepAlive叠加', async () => {
 const h=harness(false), queries=[]
 h.api.listFolders=async(_project,params)=>{queries.push({...params});return {rows:[],total:90,hasNext:false}}
 h.mount(); h.activate(); await new Promise(setImmediate); assert.equal(queries.length,0)
 h.visible.value=true; await new Promise(setImmediate); assert.ok(queries.length>0)
 h.state.search.value='目录筛选'; h.state.page.value=2
 h.visible.value=false; const count=queries.length; await h.state.refresh(); await h.state.loadTree(); assert.equal(queries.length,count)
 h.deactivate(); h.visible.value=true; await new Promise(setImmediate); assert.equal(queries.length,count)
 h.activate(); await new Promise(setImmediate); assert.equal(h.state.search.value,'目录筛选'); assert.equal(h.state.page.value,2)
 assert.ok(queries.length>count); h.close()
})

test('v-show隐藏目录页时，未完成删除确认不能发请求', async () => {
 const h=harness(); h.api.listFolders=async()=>({rows:[],total:0,hasNext:false})
 const deleting=h.state.remove({id:'7',revision:'1',name:'目录'})
 h.visible.value=false; h.visible.value=true; h.confirmations[0](); await deleting
 assert.equal(h.actions.length,0); assert.equal(h.state.pending.value,false); h.close()
})
