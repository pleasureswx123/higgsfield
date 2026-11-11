const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code = code; this.errorCode = errorCode } }
const tick = () => new Promise(resolve => setImmediate(resolve))

test('设置主图移到首位，保留其余顺序、选中状态及连续序号', async () => {
  const c = setup(); await tick()
  c.state.addReferenceMedia({ kind: 'asset', projectId: '99', assetVersionIds: ['v1', 'v2', 'v3'], allowedMediaRoles: ['reference_image'] })
  c.state.selectedVersion.value = 'v3'
  c.state.primary('v3')
  assert.deepEqual(Array.from(c.state.fields.media, item => item.assetVersionId), ['v3', 'v1', 'v2'])
  assert.deepEqual(Array.from(c.state.fields.media, item => item.ordinal), [0, 1, 2])
  assert.deepEqual(Array.from(c.state.fields.media, item => item.isPrimary), [true, false, false])
  assert.equal(c.state.selectedVersion.value, 'v3')
  const snapshot = JSON.stringify(c.state.fields.media)
  c.state.primary('missing')
  assert.equal(JSON.stringify(c.state.fields.media), snapshot)
  c.close()
})
test('旧修订主图加载即置顶，移动不越过主图，保存重开顺序不变', async () => {
  let media = [
    { assetVersionId: 'a', ordinal: 0, isPrimary: false },
    { assetVersionId: 'b', ordinal: 1, isPrimary: true },
    { assetVersionId: 'c', ordinal: 2, isPrimary: false },
  ]
  const api = {
    readElement: async () => ({ data: {
      element: { projectId: '99', name: '角色', alias: 'role', category: 'character', workStatus: 'none', revision: '7', allowedActions: ['element:edit'] },
      currentRevision: { description: '', label: '', media, propertyValues: [], propertySnapshot: [] },
    } }),
    saveElement: async (_id, _revision, payload) => { media = payload.media },
  }
  const c = setup(api, async () => {}, '5'); await tick()
  const ids = () => Array.from(c.state.fields.media, item => item.assetVersionId)
  assert.deepEqual(ids(), ['b', 'a', 'c'])
  assert.equal(c.state.dirty.value, false)
  c.state.moveMedia('b', 1); c.state.moveMedia('a', -1)
  assert.deepEqual(ids(), ['b', 'a', 'c'])
  c.state.moveMedia('c', -1)
  assert.deepEqual(ids(), ['b', 'c', 'a'])
  await c.state.save(); c.close()
  const reopened = setup(api, async () => {}, '5'); await tick()
  assert.deepEqual(Array.from(reopened.state.fields.media, item => item.assetVersionId), ['b', 'c', 'a'])
  assert.deepEqual(Array.from(reopened.state.fields.media, item => item.ordinal), [0, 1, 2])
  reopened.close()
})

test('共享选择器加入固定素材版本，去重并保留主图及已填表单', async () => {
  const c = setup(); await tick()
  assert.equal(c.state.canEdit.value, true, c.state.error.value)
  c.state.fields.name = '保留名称'; c.state.fields.description = '保留描述'
  const candidate = { kind: 'asset', projectId: '99', assetVersionIds: ['v1'], allowedMediaRoles: ['reference_image'] }
  c.state.addReferenceMedia(candidate)
  c.state.addReferenceMedia({ ...candidate, assetVersionIds: ['v1', 'v2', 'v2'] })
  c.state.addReferenceMedia({ ...candidate, assetVersionIds: ['v3'] })
  c.state.addReferenceMedia({ ...candidate, assetVersionIds: ['video'], allowedMediaRoles: ['reference_video'] })
  assert.equal(c.state.fields.media.length, 3)
  assert.equal(c.state.fields.media[0].isPrimary, true)
  assert.equal(c.state.fields.media[1].isPrimary, false)
  assert.deepEqual(Array.from(c.state.fields.media, item => item.ordinal), [0, 1, 2])
  assert.equal(c.state.fields.name, '保留名称'); assert.equal(c.state.fields.description, '保留描述')
  c.state.addReferenceMedia({ ...candidate, projectId: 'other', assetVersionIds: ['bad'] })
  c.state.addReferenceMedia({ ...candidate, allowedMediaRoles: [], assetVersionIds: ['bad'] })
  assert.equal(c.state.fields.media.length, 3)
  c.state.removeMedia('v3')
  assert.equal(c.state.selectedVersion.value, 'v1')
  c.state.removeMedia('v1')
  assert.equal(c.state.fields.media.length, 1)
  assert.equal(c.state.fields.media[0].assetVersionId, 'v2')
  assert.equal(c.state.fields.media[0].isPrimary, true)
  assert.equal(c.state.fields.media[0].ordinal, 0)
  c.state.removeMedia('v2')
  assert.equal(c.state.fields.media.length, 0)
  assert.equal(c.state.selectedVersion.value, '')
  c.state.addReferenceMedia({ ...candidate, assetVersionIds: ['video'], allowedMediaRoles: ['reference_video'] })
  c.state.addReferenceMedia(candidate)
  assert.equal(c.state.fields.media.length, 1)
  assert.equal(c.state.fields.media[0].assetVersionId, 'video')
  c.state.removeMedia('video')
  c.visible.value = false
  c.state.addReferenceMedia({ ...candidate, assetVersionIds: ['hidden'] })
  assert.equal(c.state.fields.media.length, 0); c.close()
})
test('新建元素不自动带入项目定义，移除后重新新建也不会出现', async () => {
  const api = { listProperties: async () => ({ rows: [{ id: 'p1', propertyKey: 'note', name: '备注', versionNo: 1 }], hasNext: false }) }
  const first = setup(api); await tick()
  assert.equal(first.state.properties.value.length, 0)
  first.state.properties.value.push({ definition: (await api.listProperties()).rows[0], value: null })
  first.state.removeProperty('p1'); assert.equal(first.state.properties.value.length, 0); first.close()
  const next = setup(api); await tick()
  assert.equal(next.state.properties.value.length, 0); next.close()
})
test('移除属性仅改变当前元素，保存后再打开不会从项目定义补回，空属性仍可保留', async () => {
  const definition = { id: 'p1', propertyKey: 'note', versionNo: 1, name: '备注', valueType: 'text', options: [] }
  let snapshot = [{ ...definition, definitionId: 'p1', definitionVersion: 1, value: null }]
  const api = {
    listProperties: async () => ({ rows: [definition], hasNext: false }),
    readElement: async () => ({ data: {
      element: { projectId: '99', name: '角色', alias: 'role', category: 'character', workStatus: 'none', revision: '7', allowedActions: ['element:edit'] },
      currentRevision: { description: '', label: '', media: [], propertyValues: [], propertySnapshot: snapshot },
    } }),
    saveElement: async (_id, _revision, payload) => {
      snapshot = payload.propertyValues.map(value => ({ ...definition, ...value }))
    },
  }
  const c = setup(api, async () => {}, '5'); await tick()
  await c.state.save(); assert.equal(snapshot.length, 1)
  assert.equal(snapshot[0].value, null)
  c.state.removeProperty('p1')
  assert.equal(c.state.properties.value.length, 0)
  await c.state.save(); assert.equal(snapshot.length, 0); c.close()
  const reopened = setup(api, async () => {}, '5'); await tick()
  assert.equal(reopened.state.properties.value.length, 0)
  assert.equal((await api.listProperties()).rows.length, 1)
  reopened.close()
})
function setup(overrides = {}, confirm = async () => {}, elementId = null) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one' }), visible = vue.ref(true)
  let writes = 0, completed = 0
  const api = { listProperties: async () => ({ rows: [], hasNext: false }), createElement: async () => { writes++ }, ...overrides }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useElementEditor.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, Error, AbortController, crypto: { randomUUID }, window: { addEventListener() {}, removeEventListener() {} }, URL,
    require(id) {
      if (id === 'vue') return { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onActivated: fn => { hooks.activate = fn } }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn }, onBeforeRouteUpdate: fn => { hooks.update = fn } }
      if (id === 'element-plus') return { ElMessageBox: { confirm } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/api/client') return { ApiError }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useElementEditor('99', elementId, vue.ref(['element:create']), () => { completed++ }, () => visible.value))
  state.form.value = { validate: async () => true }
  return { state, hooks, auth, visible, writes: () => writes, completed: () => completed, close: () => { hooks.unmount(); scope.stop() } }
}

test('元素未保存修改切换项目可取消，同项目页签不触发确认', async () => {
  const c = setup({}, async () => { throw new Error('取消') }); await tick()
  c.state.fields.name = '角色'
  assert.equal(await c.hooks.update({ params: { id: '100' } }, { params: { id: '99' } }), false)
  assert.equal(c.hooks.update({ params: { id: '99' } }, { params: { id: '99' } }), true)
  assert.equal(c.state.fields.name, '角色'); c.close()
})

test('账号变化后迟到初始化不能恢复编辑权限或属性', async () => {
  let resolve
  const c = setup({ listProperties: () => new Promise(done => { resolve = done }) })
  c.auth.token = 'two'
  resolve({ rows: [{ id: 'private', propertyKey: 'secret' }], hasNext: false }); await tick()
  assert.equal(c.state.canEdit.value, false); assert.equal(c.state.properties.value.length, 0); c.close()
})

test('校验期间切换账号不提交，保存返回后切换账号不触发完成回调', async () => {
  let validate
  const c = setup(); await tick(); c.state.fields.name = '角色'
  c.state.form.value = { validate: () => new Promise(done => { validate = done }) }
  const pending = c.state.save(); c.auth.token = 'two'; validate(true); await pending
  assert.equal(c.writes(), 0); c.close()
  let resolve
  const d = setup({ createElement: () => new Promise(done => { resolve = done }) }); await tick()
  d.state.fields.name = '角色'; const saving = d.state.save(); await tick()
  d.auth.token = 'two'; resolve({}); await saving
  assert.equal(d.completed(), 0); assert.match(d.state.error.value, /登录状态/); d.close()
})

test('切换会话清空元素正文、成员和候选，禁止继续读取旧项目素材', async () => {
  let reads = 0
  const c = setup({ listAssets: async () => { reads++; return { rows: [{ id: 'asset' }], total: 1 } } }); await tick()
  c.state.fields.name = '旧角色'; c.state.fields.description = '旧正文'
  c.state.members.value = [{ userId: 'old' }]; c.state.properties.value = [{ definition: { id: 'private' }, value: '秘密' }]
  c.state.showPicker(); await tick(); assert.equal(reads, 1)
  c.auth.token = 'two'
  assert.equal(c.state.fields.name, ''); assert.equal(c.state.fields.description, '')
  assert.equal(c.state.members.value.length, 0); assert.equal(c.state.properties.value.length, 0)
  assert.equal(c.state.candidates.value.length, 0); assert.equal(c.state.pickerTotal.value, 0)
  assert.equal(c.state.pickerOpen.value, false); assert.equal(c.state.dirty.value, false)
  c.state.showPicker(); await tick(); assert.equal(reads, 1)
  c.close()
})

test('保存结果未知时冻结原正文和幂等键，确认成功后解除锁定', async () => {
  const calls = []
  const c = setup({ createElement: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('响应丢失') } }); await tick()
  c.state.fields.name = '原角色'; await c.state.save()
  assert.equal(c.state.uncertain.value, true); assert.equal(await c.state.confirmClose(), false)
  c.state.fields.name = '意外改动'; await c.state.save()
  assert.equal(calls[0][2], calls[1][2]); assert.equal(calls[1][1].name, '原角色')
  assert.equal(c.completed(), 1); assert.equal(c.state.locked.value, false); c.close()
})

test('明确业务拒绝释放保存意图，处理中仍保留原请求', async () => {
  for (const code of ['REVISION_CONFLICT', 'IDEMPOTENCY_IN_PROGRESS']) {
    let calls = 0
    const c = setup({ createElement: async () => { calls++; throw new ApiError('拒绝', 601, code) } }); await tick()
    c.state.fields.name = '角色'; await c.state.save()
    assert.equal(c.state.uncertain.value, code === 'IDEMPOTENCY_IN_PROGRESS')
    assert.equal(c.state.conflict.value, code === 'REVISION_CONFLICT')
    await c.state.save(); assert.equal(calls, code === 'REVISION_CONFLICT' ? 1 : 2)
    assert.equal(c.state.fields.name, '角色'); c.close()
  }
})

test('删除结果未知时禁止保存，重试使用原修订和原幂等键', async () => {
  const calls = []; let confirms = 0
  const c = setup({
    readElement: async () => ({ data: {
      element: { projectId: '99', name: '角色', alias: 'role', category: 'character', workStatus: 'none', performerId: null, revision: '7', allowedActions: ['element:edit', 'element:remove'] },
      currentRevision: { description: '', label: '', media: [], propertyValues: [], propertySnapshot: [] },
    } }),
    recycleElement: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('响应丢失') },
    saveElement: async () => { throw new Error('不应保存') },
  }, async () => { confirms++ }, '5'); await tick()
  await c.state.remove(); assert.equal(c.state.uncertain.value, true)
  assert.equal(await c.state.confirmClose(), false)
  await c.state.save(); assert.equal(c.state.error.value, '响应丢失')
  c.state.detail.value.element.revision = '8'
  await c.state.retry()
  assert.equal(confirms, 1); assert.equal(calls.length, 2)
  assert.equal(calls[1][1], '7'); assert.equal(calls[1][3], calls[0][3])
  assert.equal(c.state.uncertain.value, false); assert.equal(c.completed(), 1); c.close()
})

test('隐藏元素编辑器保留未知保存，返回后原请求确认且迟到结果不干扰', async () => {
  const calls = [], resolvers = []
  const c = setup({ createElement: (...args) => { calls.push(args); return new Promise(done => { resolvers.push(done) }) } }); await tick()
  c.state.fields.name = '角色'; const first = c.state.save(); await tick()
  c.hooks.deactivate(); await c.state.save(); assert.equal(calls.length, 1)
  assert.equal(c.state.canEdit.value, false); assert.equal(c.state.uncertain.value, true)
  c.hooks.activate(); const second = c.state.retry(); await tick()
  assert.equal(calls.length, 2); assert.equal(calls[0][2], calls[1][2])
  resolvers[0]({}); await first
  assert.equal(c.state.saving.value, true); assert.equal(c.completed(), 0)
  resolvers[1]({}); await second
  assert.equal(c.completed(), 1); c.close()
})

test('新建名称自动建议别名，分类版本联动，手动覆盖后可重置', async () => {
  const c = setup(); await tick()
  c.state.fields.name = '主角 Alice'; assert.equal(c.state.fields.alias, 'char_主角_alice')
  c.state.fields.category = 'scene'; c.state.fields.label = 'V2'
  assert.equal(c.state.fields.alias, 'scene_主角_alice_v2')
  c.state.markAliasManual(); c.state.fields.alias = 'custom'
  c.state.fields.name = '新版名称'; assert.equal(c.state.fields.alias, 'custom')
  c.state.resetAliasSuggestion(); assert.equal(c.state.fields.alias, 'scene_新版名称_v2')
  c.state.fields.name = '长'.repeat(200); assert.equal(Array.from(c.state.fields.alias).length, 100)
  c.close()
})

test('只填写名称可提交无图元素，别名冲突定位字段并保留手动修正', async () => {
  const calls = []
  const c = setup({ createElement: async (...args) => { calls.push(args); throw new ApiError('别名已存在', 601, 'ALIAS_CONFLICT') } }); await tick()
  c.state.fields.name = '无图角色'; await c.state.save()
  assert.equal(calls[0][1].alias, 'char_无图角色'); assert.equal(calls[0][1].media.length, 0)
  assert.equal(c.state.aliasError.value, '别名已存在'); assert.equal(c.state.uncertain.value, false)
  c.state.fields.name = '新名称'; assert.equal(c.state.fields.alias, 'char_无图角色')
  c.state.fields.alias = 'manual-new'; assert.equal(c.state.aliasError.value, '')
  c.close()
})

test('隐藏后重新打开不接受旧关闭确认，必须重新确认当前草稿', async () => {
  const confirmations = []
  const c = setup({}, () => new Promise(resolve => confirmations.push(resolve))); await tick()
  c.state.fields.name = '角色'
  const previous = c.state.confirmClose()
  c.hooks.deactivate(); c.hooks.activate()
  confirmations[0](); assert.equal(await previous, false)
  assert.equal(c.state.fields.name, '角色')
  const current = c.state.confirmClose(); confirmations[1]()
  assert.equal(await current, true); c.close()
})

test('隐藏再显示后旧属性升级确认不能修改当前属性，新确认仍可升级', async () => {
  const confirmations = []
  const c = setup({}, () => new Promise(resolve => confirmations.push(resolve))); await tick()
  c.state.properties.value = [{ definition: { id: 'p', name: '服装', versionNo: 1, valueType: 'text' }, value: '蓝色' }]
  c.state.newerDefinitions.value = { p: { id: 'p', name: '服装', versionNo: 2, valueType: 'single_select', options: ['红色'] } }
  const previous = c.state.adoptDefinition('p')
  c.hooks.deactivate(); c.hooks.activate(); confirmations[0](); await previous
  assert.equal(c.state.properties.value[0].definition.versionNo, 1)
  assert.equal(c.state.properties.value[0].value, '蓝色')
  assert.equal(c.state.newerDefinitions.value.p.versionNo, 2)
  const current = c.state.adoptDefinition('p'); confirmations[1](); await current
  assert.equal(c.state.properties.value[0].definition.versionNo, 2)
  assert.equal(c.state.properties.value[0].value, null)
  c.close()
})

test('元素编辑页签隐藏保留字段且旧校验失效，缓存未激活不恢复编辑',async()=>{
 const c=setup();await tick();c.state.fields.name='保留名称';c.state.fields.description='保留正文'
 let validate;c.state.form.value={validate:()=>new Promise(resolve=>{validate=resolve})}
 const saving=c.state.save();c.visible.value=false
 assert.equal(c.state.canEdit.value,false);assert.equal(c.state.active.value,false)
 c.visible.value=true;validate(true);await saving
 assert.equal(c.writes(),0);assert.equal(c.state.fields.name,'保留名称');assert.equal(c.state.fields.description,'保留正文')
 assert.equal(c.state.dirty.value,true)
 c.hooks.deactivate();c.visible.value=false;c.visible.value=true
 assert.equal(c.state.active.value,false);c.hooks.activate();assert.equal(c.state.canEdit.value,true)
 c.close()
})

test('制作状态同步只更新元数据和修订，保留未保存描述及正确dirty基线', async () => {
  const c = setup({ readElement: async () => ({ data: {
    element: { id: '5', projectId: '99', name: '角色', alias: 'role', category: 'character', workStatus: 'none', performerId: null, revision: '7', allowedActions: ['element:edit'] },
    currentRevision: { description: '原描述', label: '', media: [], propertyValues: [], propertySnapshot: [] },
  } }) }, async () => {}, '5')
  await tick()
  c.state.syncProduction({ targetId: '5', revision: '8', workStatus: 'working', performerId: 'u', performerName: '制作人' })
  assert.equal(c.state.dirty.value, false)
  c.state.productionBusy.value = true
  assert.equal(c.state.locked.value, true)
  c.state.productionBusy.value = false
  c.state.fields.description = '未保存描述'
  c.state.syncProduction({ targetId: '5', revision: '9', workStatus: 'review', performerId: 'u', performerName: '制作人' })
  assert.equal(c.state.fields.description, '未保存描述')
  assert.equal(c.state.detail.value.element.revision, '9')
  assert.equal(c.state.dirty.value, true)
  c.state.fields.description = '原描述'
  assert.equal(c.state.dirty.value, false)
  c.close()
})
