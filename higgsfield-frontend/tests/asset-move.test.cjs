const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'),
  vue = require('vue')
const tick = async () => {
  await vue.nextTick()
  await new Promise((resolve) => setImmediate(resolve))
}
function harness(kind = 'media', confirm = async () => {}) {
  const exports = {},
    calls = [],
    creates = [],
    canCreate = vue.ref(true),
    visible = vue.ref(true),
    folderReads = [],
    directories = [],
    changes = [],
    auth = vue.reactive({ token: 'one' }),
    allowed = vue.ref(true)
  let changed = 0,
    guard,
    updateGuard,
    unmount,
    activate,
    deactivate,
    keys = 0
  class ApiError extends Error {
    constructor(message, code, errorCode) {
      super(message)
      this.code = code
      this.errorCode = errorCode
    }
  }
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/useDirectoryMove.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
    ).outputText,
    {
      exports,
      Error,
      AbortController,
      crypto: { randomUUID: () => String(++keys) },
      require(name) {
        if (name === 'vue')
          return {
            ...vue,
            onBeforeUnmount: (fn) => {
              unmount = fn
            },
            onActivated: (fn) => {
              activate = fn
            },
            onDeactivated: (fn) => {
              deactivate = fn
            },
          }
        if (name === 'vue-router')
          return {
            onBeforeRouteLeave: (fn) => {
              guard = fn
            },
            onBeforeRouteUpdate: (fn) => {
              updateGuard = fn
            },
          }
        if (name.includes('stores/auth')) return { useAuthStore: () => auth }
        if (name.includes('client')) return { ApiError }
        if (name === 'element-plus') return { ElMessageBox: { confirm } }
        return {
          createFolder: (...args) => new Promise((resolve, reject) => creates.push({ args, resolve, reject })),
          readFolder: (...args) =>
            new Promise((resolve, reject) => folderReads.push({ args, resolve, reject })),
          listFolders: async (...args) => {
            directories.push(args)
            return { rows: [], hasNext: false }
          },
          moveElement: (...args) =>
            new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
          moveLibraryEntry: (...args) =>
            new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
        }
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() =>
      exports.useDirectoryMove(
        '9007199254740993',
        () => allowed.value,
        (ids, summary) => {
          changed++
          changes.push({ ids, summary })
        },
        kind,
        () => canCreate.value,
        () => visible.value,
      ),
    )
  return {
    creates, canCreate, visible,
    state,
    calls,
    folderReads,
    directories,
    changes,
    auth,
    allowed,
    ApiError,
    activate: () => activate(),
    deactivate: () => deactivate(),
    updateGuard: () =>
      updateGuard({ fullPath: '/project?tab=other' }, { fullPath: '/project?tab=assets' }),
    guard: () => guard(),
    changed: () => changed,
    close() {
      unmount()
      scope.stop()
    },
  }
}
test('素材移动冻结目录归属修订和幂等键，不确定结果只重试原请求', async () => {
  const h = harness(),
    entry = { id: '9007199254740995', revision: '7', folderId: '4', name: '素材' }
  h.state.open(entry)
  await tick()
  const first = h.state.save()
  h.calls[0].reject(new Error('网络中断'))
  await first
  assert.equal(h.state.uncertain.value, true)
  assert.equal(h.guard(), false)
  h.state.navigate([{ id: '9' }])
  assert.equal(h.state.path.value.length, 0)
  h.state.close()
  assert.notEqual(h.state.entry.value, null)
  entry.revision = '8'
  const retry = h.state.save()
  assert.equal(h.calls[1].args[2], h.calls[0].args[2])
  assert.equal(h.calls[1].args[1].revision, '7')
  assert.equal(h.calls[1].args[1].entryId, entry.id)
  assert.equal(h.calls[1].args[1].folderId, null)
  h.calls[1].resolve({ data: {} })
  await retry
  assert.equal(h.changed(), 1)
  assert.equal(h.state.entry.value, null)
  assert.equal(h.guard(), true)
  h.close()
})

test('缓存停用保留不确定请求，恢复后使用原键和原快照重试', async () => {
  const h = harness(),
    source = { id: '1', revision: '2', folderId: '3' }
  h.state.open(source)
  await tick()
  source.revision = '99'
  const pending = h.state.save()
  assert.equal(h.updateGuard(), false)
  h.deactivate()
  assert.equal(h.state.active.value, false)
  h.calls[0].reject(new Error('断网'))
  await pending
  await h.state.save()
  assert.equal(h.calls.length, 1)
  h.activate()
  assert.equal(h.state.uncertain.value, true)
  const retry = h.state.save()
  assert.equal(h.calls[1].args[2], h.calls[0].args[2])
  assert.equal(h.calls[1].args[1].revision, '2')
  h.calls[1].resolve({})
  await retry
  assert.equal(h.changed(), 1)
  assert.equal(h.updateGuard(), true)
  h.close()
})

test('停用期间移动成功只在激活时刷新，账号变化清除待刷新状态', async () => {
  const h = harness()
  h.state.open({ id: '1', revision: '2', folderId: '3' })
  await tick()
  const pending = h.state.save()
  h.deactivate()
  h.calls[0].resolve({})
  await pending
  assert.equal(h.changed(), 0)
  assert.equal(h.state.entry.value, null)
  h.activate()
  h.activate()
  assert.equal(h.changed(), 1)
  h.state.open({ id: '2', revision: '2', folderId: '3' })
  await tick()
  const second = h.state.save()
  h.deactivate()
  h.calls[1].resolve({})
  await second
  h.auth.token = ''
  h.activate()
  assert.equal(h.changed(), 1)
  h.state.open({ id: '3', revision: '1', folderId: '3' })
  await h.state.save()
  assert.equal(h.calls.length, 2)
  assert.equal(h.state.entry.value, null)
  h.close()
})
test('同目录不提交，撤权禁止写入，账号切换隔离迟到成功', async () => {
  const h = harness()
  h.state.open({ id: '1', revision: '1', folderId: null })
  await tick()
  await h.state.save()
  assert.equal(h.calls.length, 0)
  h.state.navigate([{ id: '2' }])
  await tick()
  h.allowed.value = false
  await h.state.save()
  assert.equal(h.calls.length, 0)
  h.allowed.value = true
  await tick()
  const pending = h.state.save()
  h.auth.token = 'two'
  assert.equal(h.calls[0].args[3].aborted, true)
  h.calls[0].resolve({ data: {} })
  await pending
  assert.equal(h.changed(), 0)
  assert.equal(h.state.entry.value, null)
  h.close()
})

test('元素移动仅查询元素目录，冻结原修订并按元素接口重试', async () => {
  const h = harness('element'),
    source = { id: '9007199254740995', name: '角色', revision: '7', folderId: '4' }
  h.state.open(source)
  await tick()
  assert.equal(h.directories[0][1].folderKind, 'element')
  h.state.navigate([{ id: '9', name: '目标' }])
  await tick()
  const pending = h.state.save()
  source.revision = '8'
  source.folderId = '10'
  assert.equal(h.calls[0].args[0], source.id)
  assert.equal(h.calls[0].args[1].folderId, '9')
  assert.equal(h.calls[0].args[1].revision, '7')
  assert.equal('entryId' in h.calls[0].args[1], false)
  h.calls[0].reject(new Error('超时'))
  await pending
  h.state.navigate([])
  assert.equal(h.state.path.value[0].id, '9')
  const retry = h.state.save()
  assert.equal(h.calls[1].args[2], h.calls[0].args[2])
  assert.equal(h.calls[1].args[1].revision, '7')
  h.calls[1].resolve({})
  await retry
  assert.equal(h.changed(), 1)
  assert.equal(h.state.entry.value, null)
  h.close()
})

test('批量移动跳过同目录项，部分失败仅重试原目标原修订，不重复成功项', async () => {
  const h = harness(),
    one = { id: '1', name: '甲', revision: '2', folderId: '4' },
    two = { id: '2', name: '乙', revision: '3', folderId: '5' }
  h.state.openMany([one, two, { id: '3', name: '已在根目录', revision: '6', folderId: null }])
  await tick()
  const run = h.state.save()
  assert.equal(h.calls.length, 1)
  one.revision = '99'
  two.revision = '99'
  h.calls[0].resolve({})
  await tick()
  assert.equal(h.calls.length, 2)
  h.calls[1].reject(new Error('网络中断'))
  await run
  assert.equal(h.state.entries.value.length, 1)
  assert.equal(h.state.entries.value[0].id, '2')
  assert.equal(h.changes[0].ids.length, 1)
  assert.equal(h.changes[0].ids[0], '1')
  assert.match(h.changes[0].summary, /1 项已在目标目录/)
  assert.equal(h.guard(), false)
  h.state.navigate([{ id: '8' }])
  assert.equal(h.state.path.value.length, 0)
  const retry = h.state.save()
  assert.equal(h.calls.length, 3)
  assert.equal(h.calls[2].args[1].entryId, '2')
  assert.equal(h.calls[2].args[1].revision, '3')
  assert.equal(h.calls[2].args[1].folderId, null)
  assert.equal(h.calls[2].args[2], h.calls[1].args[2])
  h.calls[2].resolve({})
  await retry
  assert.equal(h.state.entry.value, null)
  assert.equal(h.changed(), 2)
  assert.equal(h.guard(), true)
  h.close()
})

test('批量移动缓存停用后停止剩余项，恢复时保持未执行项的原修订', async () => {
  const h = harness(),
    second = { id: '2', name: '乙', revision: '3', folderId: '4' }
  h.state.openMany([{ id: '1', name: '甲', revision: '2', folderId: '4' }, second])
  await tick()
  const run = h.state.save()
  h.deactivate()
  h.calls[0].resolve({})
  await run
  assert.equal(h.calls.length, 1)
  assert.equal(h.changed(), 0)
  assert.equal(h.state.entries.value[0].id, '2')
  second.revision = '10'
  h.activate()
  assert.equal(h.changed(), 1)
  const retry = h.state.save()
  assert.equal(h.calls[1].args[1].revision, '3')
  h.calls[1].resolve({})
  await retry
  assert.equal(h.changed(), 2)
  assert.equal(h.state.entry.value, null)
  h.close()
})

test('批量移动明确冲突允许关闭，撤权不继续提交后续项', async () => {
  const h = harness()
  h.state.openMany([
    { id: '1', name: '甲', revision: '2', folderId: '4' },
    { id: '2', name: '乙', revision: '3', folderId: '4' },
  ])
  await tick()
  const run = h.state.save()
  h.calls[0].reject(new h.ApiError('版本冲突', 601, 'REVISION_CONFLICT'))
  await tick()
  h.calls[1].resolve({})
  await run
  assert.equal(h.state.locked.value, false)
  assert.match(h.state.error.value, /版本冲突/)
  h.state.close()
  assert.equal(h.state.entry.value, null)
  h.state.openMany([
    { id: '3', name: '丙', revision: '2', folderId: '4' },
    { id: '4', name: '丁', revision: '3', folderId: '4' },
  ])
  await tick()
  const second = h.state.save()
  h.allowed.value = false
  h.calls[2].resolve({})
  await second
  assert.equal(h.calls.length, 3)
  assert.equal(h.state.entries.value[0].id, '4')
  await h.state.save()
  assert.equal(h.calls.length, 3)
  h.close()
})

test('元素批量移动逐项使用元素接口，部分失败保留原修订和键', async () => {
  const h = harness('element')
  h.state.openMany([
    { id: '9007199254740993', name: '甲', revision: '2', folderId: '4' },
    { id: '9007199254740994', name: '乙', revision: '3', folderId: '4' },
  ])
  await tick()
  assert.equal(h.directories[0][1].folderKind, 'element')
  const run = h.state.save()
  h.calls[0].resolve({})
  await tick()
  assert.equal(h.calls[1].args[0], '9007199254740994')
  assert.equal(h.calls[1].args[1].revision, '3')
  assert.equal(h.calls[1].args[1].folderId, null)
  assert.equal('entryId' in h.calls[1].args[1], false)
  h.calls[1].reject(new Error('断网'))
  await run
  const retry = h.state.save()
  assert.equal(h.calls[2].args[2], h.calls[1].args[2])
  assert.equal(h.calls[2].args[0], '9007199254740994')
  h.calls[2].resolve({})
  await retry
  assert.equal(h.state.entries.value.length, 0)
  assert.equal(h.changed(), 2)
  h.close()
})

test('移动目录搜索排序保留当前位置，搜索结果读取真实祖先后才能提交', async () => {
  const h = harness('element'),
    projectId = '9007199254740993'
  h.state.open({ id: '1', name: '角色', revision: '2', folderId: null })
  await tick()
  h.state.navigate([{ id: '10', name: '旧目录' }])
  await tick()
  h.state.q.value = '  目标  '
  h.state.search()
  await tick()
  let params = h.directories.at(-1)[1]
  assert.equal(params.q, '目标')
  assert.equal(params.parentId, undefined)
  assert.equal(params.folderKind, 'element')
  assert.equal(h.state.path.value[0].id, '10')
  await h.state.save()
  assert.equal(h.calls.length, 0)
  h.state.changeSort('updatedDesc')
  await tick()
  assert.equal(h.directories.at(-1)[1].sort, 'updatedDesc')
  assert.equal(h.directories.at(-1)[1].pageNum, 1)
  const target = { id: '12', name: '目标', projectId, folderKind: 'element' },
    parent = { id: '11', name: '真实父目录', projectId, folderKind: 'element' }
  const selecting = h.state.selectFolder(target)
  h.folderReads[0].resolve({ data: { folder: target, ancestors: [parent] } })
  await selecting
  await tick()
  assert.equal(h.state.path.value.map((x) => x.id).join(','), '11,12')
  assert.equal(h.state.searching.value, false)
  assert.equal(h.directories.at(-1)[1].parentId, '12')
  const saving = h.state.save()
  assert.equal(h.calls[0].args[1].folderId, '12')
  h.calls[0].resolve({})
  await saving
  h.close()
})

test('搜索目标拒绝跨项目并隔离停用后的迟到路径，不影响原目标', async () => {
  const h = harness()
  h.state.open({ id: '1', name: '图片', revision: '2', folderId: '3' })
  await tick()
  h.state.q.value = '目标'
  h.state.search()
  await tick()
  const first = h.state.selectFolder({ id: '12' })
  h.folderReads[0].resolve({
    data: { folder: { id: '12', projectId: 'other', folderKind: 'media' }, ancestors: [] },
  })
  await first
  assert.match(h.state.error.value, /不属于/)
  assert.equal(h.state.path.value.length, 0)
  const second = h.state.selectFolder({ id: '12' })
  h.deactivate()
  h.folderReads[1].resolve({
    data: {
      folder: { id: '12', projectId: '9007199254740993', folderKind: 'media' },
      ancestors: [],
    },
  })
  await second
  assert.equal(h.state.path.value.length, 0)
  assert.equal(h.folderReads[1].args[1].aborted, true)
  h.close()
})

test('未确认移动撤权后允许离开并禁止重试，恢复权限仍使用原快照和键', async () => {
  const h = harness()
  h.state.open({ id: '1', revision: '2', folderId: '3', name: '素材' })
  await tick()
  const pending = h.state.save()
  h.calls[0].reject(new Error('响应丢失'))
  await pending
  h.allowed.value = false
  assert.equal(h.guard(), true)
  assert.equal(h.updateGuard(), true)
  assert.equal(h.state.rows.value.length, 0)
  await h.state.save()
  assert.equal(h.calls.length, 1)
  h.allowed.value = true
  assert.equal(h.guard(), false)
  const retry = h.state.save()
  assert.equal(h.calls[1].args[2], h.calls[0].args[2])
  assert.deepEqual(h.calls[1].args[1], h.calls[0].args[1])
  h.calls[1].resolve({})
  await retry
  assert.equal(h.guard(), true)
  h.close()
})

test('普通移动选择撤权恢复后重新读取目标目录，停用后允许路由离开', async () => {
  const h = harness()
  h.state.open({ id: '1', revision: '2', folderId: '3', name: '素材' })
  await tick()
  const reads = h.directories.length
  h.allowed.value = false
  h.allowed.value = true
  await tick()
  assert.equal(h.directories.length, reads + 1)
  const pending = h.state.save()
  h.deactivate()
  assert.equal(h.guard(), true)
  assert.equal(h.updateGuard(), true)
  h.calls[0].reject(new Error('响应丢失'))
  await pending
  h.close()
})

test('移动目标内联新建按目录种类和当前位置创建，成功进入但不自动移动', async () => {
 for (const kind of ['media','element']) {
  const h=harness(kind); h.state.open({id:'e',revision:'1',folderId:null,name:'条目'}); await tick()
  h.state.navigate([{id:'parent',name:'父目录'}]); await tick(); h.state.startCreate()
  h.state.newFolder.name='新目录'; h.state.newFolder.description='用途'; h.state.newFolder.color='pink'
  h.state.createForm.value={validate:async()=>true}
  const creating=h.state.submitCreate(); await tick()
  assert.equal(h.creates[0].args[1].parentId,'parent'); assert.equal(h.creates[0].args[1].folderKind,kind)
  assert.equal(h.creates[0].args[1].color,'pink'); assert.equal(h.state.locked.value,true)
  await h.state.save(); assert.equal(h.calls.length,0)
  h.creates[0].resolve({data:{id:'new',name:'新目录'}}); await creating
  assert.equal(h.state.path.value.at(-1).id,'new'); assert.equal(h.calls.length,0)
  assert.match(h.state.report.value,/请确认/); assert.equal(h.state.createOpen.value,false); h.close()
 }
})

test('目录创建响应未知冻结父级内容与键，确认原请求后允许移动', async () => {
 const h=harness(); h.state.open({id:'e',revision:'1',folderId:null,name:'条目'}); await tick(); h.state.startCreate()
 h.state.newFolder.name='原目录'; h.state.createForm.value={validate:async()=>true}
 const first=h.state.submitCreate(); await tick(); h.creates[0].reject(new Error('中断')); await first
 h.state.newFolder.name='意外修改'; h.state.navigate([{id:'other'}]); h.state.cancelCreate()
 assert.equal(h.state.createOpen.value,true); assert.equal(h.state.path.value.length,0)
 const retry=h.state.submitCreate(); await tick()
 assert.equal(h.creates[1].args[1].name,'原目录'); assert.equal(h.creates[1].args[2],h.creates[0].args[2])
 h.creates[1].resolve({data:{id:'new',name:'原目录'}}); await retry
 assert.equal(h.state.locked.value,false); h.close()
})

test('新建目录权限独立控制，迟到校验及账号变化不创建或回填', async () => {
 const h=harness(); h.state.open({id:'e',revision:'1',folderId:null,name:'条目'}); await tick()
 h.canCreate.value=false; h.state.startCreate(); assert.equal(h.state.createOpen.value,false)
 h.canCreate.value=true; h.state.startCreate(); h.state.newFolder.name='新目录'
 let resolve; h.state.createForm.value={validate:()=>new Promise(done=>{resolve=done}),clearValidate(){}}
 const first=h.state.submitCreate(); await h.state.cancelCreate(); h.state.startCreate(); h.state.newFolder.name='新目录'; resolve(true); await first
 assert.equal(h.creates.length,0)
 h.state.createForm.value={validate:async()=>true}; const second=h.state.submitCreate(); await tick()
 h.auth.token='two'; h.creates[0].resolve({data:{id:'private',name:'旧账号目录'}}); await second
 assert.equal(h.state.path.value.length,0); assert.equal(h.state.createOpen.value,false); h.close()
})



test('内联目录未提交内容关闭或路由离开可取消，取消新建不移动条目', async () => {
 let accept=false
 const h=harness('media',async()=>{if(!accept)throw new Error('取消')})
 h.state.open({id:'e',revision:'1',folderId:null,name:'条目'}); await tick(); h.state.startCreate(); h.state.newFolder.name='未提交'
 await h.state.close(); assert.notEqual(h.state.entry.value,null); assert.equal(await h.guard(),false)
 await h.state.cancelCreate(); assert.equal(h.state.createOpen.value,true); assert.equal(h.state.newFolder.name,'未提交')
 accept=true; await h.state.cancelCreate(); assert.equal(h.state.createOpen.value,false)
 assert.equal(h.creates.length,0); assert.equal(h.calls.length,0); h.close()
})

test('旧目录放弃确认不跨隐藏恢复生效，创建开始后不能迟到关闭', async () => {
 let resolve
 const h=harness('media',()=>new Promise(done=>{resolve=done}))
 h.state.open({id:'e',revision:'1',folderId:null,name:'条目'}); await tick(); h.state.startCreate(); h.state.newFolder.name='目录'
 const first=h.state.close(); h.deactivate(); h.activate(); resolve(); await first
 assert.equal(h.state.createOpen.value,true); await tick()
 const second=h.state.close(); h.state.createForm.value={validate:async()=>true}
 const creating=h.state.submitCreate(); await tick(); resolve(); await second
 assert.notEqual(h.state.entry.value,null)
 h.creates[0].resolve({data:{id:'new',name:'目录'}}); await creating; h.close()
})

test('移动弹窗页签隐藏保留目标和新建草稿，缓存未激活时不恢复读取',async()=>{
 const h=harness()
 h.state.open({id:'7',revision:'3',folderId:'old',name:'素材'});await tick()
 h.state.navigate([{id:'target',name:'目标'}]);await tick()
 h.state.startCreate();h.state.newFolder.name='草稿目录'
 const count=h.directories.length
 h.visible.value=false
 assert.equal(h.state.active.value,false);assert.equal(h.state.entry.value.id,'7')
 assert.equal(h.state.path.value[0].id,'target');assert.equal(h.state.newFolder.name,'草稿目录')
 await h.state.load();await h.state.save();assert.equal(h.directories.length,count);assert.equal(h.calls.length,0)
 h.deactivate();h.visible.value=true;assert.equal(h.directories.length,count)
 h.activate();await tick();assert.equal(h.directories.length,count+1)
 assert.equal(h.state.newFolder.name,'草稿目录');assert.equal(h.state.createOpen.value,true)
 h.close()
})

test('移动批次隐藏后不继续提交，返回仅重试原目标和修订',async()=>{
 const h=harness()
 h.state.openMany([{id:'7',revision:'3',folderId:'old',name:'一'},{id:'8',revision:'4',folderId:'old',name:'二'}]);await tick()
 const save=h.state.save();assert.equal(h.calls.length,1)
 h.visible.value=false;h.calls[0].resolve({});await save
 assert.equal(h.calls.length,1);assert.equal(h.changed(),0);assert.equal(h.state.uncertain.value,true)
 h.visible.value=true;assert.equal(h.changed(),1)
 const retry=h.state.save();assert.equal(h.calls[1].args[1].entryId,'8')
 assert.equal(h.calls[1].args[1].revision,'4');assert.equal(h.calls[1].args[1].folderId,null)
 h.calls[1].resolve({});await retry;assert.equal(h.changed(),2);h.close()
})
