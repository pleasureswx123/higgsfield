const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code = code; this.errorCode = errorCode } }
const tick = () => new Promise(resolve => setImmediate(resolve))
const definition = { id: '5', propertyKey: 'color', name: '颜色', valueType: 'text', options: [], versionNo: 1 }
async function setup(overrides = {}, confirm = async () => {}) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one' }), calls = [], visible = vue.ref(true)
  let changed = 0
  const api = {
    listProperties: async () => ({ rows: [definition], total: 1 }),
    createProperty: async (...args) => { calls.push(args); return { data: definition } },
    versionProperty: async (...args) => { calls.push(args); return { data: { ...definition, versionNo: 2 } } }, ...overrides,
  }
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/usePropertyDefinitions.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, Error, AbortController, crypto: { randomUUID },
    require(id) {
      if (id === 'vue') return { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onActivated: fn => { hooks.activate = fn } }
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => { hooks.leave = fn }, onBeforeRouteUpdate: fn => { hooks.update = fn } }
      if (id === 'element-plus') return { ElMessageBox: { confirm } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/api/client') return { ApiError }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.usePropertyDefinitions('99', () => { changed++ }, () => visible.value))
  state.form.value = { validate: async () => true, clearValidate() {} }
  await tick()
  return { state, hooks, auth, calls, visible, changed: () => changed, close: () => { hooks.unmount(); scope.stop() } }
}

test('创建响应未知锁定编辑与关闭，重试冻结原正文和幂等键', async () => {
  const calls = []
  const c = await setup({ createProperty: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('中断'); return { data: definition } } })
  c.state.fields.name = '原名称'; await c.state.save()
  assert.equal(c.state.uncertain.value, true); assert.equal(await c.state.confirmDiscard(), false)
  await c.state.edit(definition); assert.equal(c.state.editing.value, undefined)
  c.state.fields.name = '意外修改'; await c.state.save()
  assert.equal(calls[1][1].name, '原名称'); assert.equal(calls[0][2], calls[1][2])
  assert.equal(c.changed(), 1); assert.equal(c.state.locked.value, false); c.close()
})

test('属性版本更新重试保留基准ID与选项', async () => {
  const calls = []
  const c = await setup({ versionProperty: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('中断'); return { data: { ...definition, versionNo: 2 } } } })
  await c.state.edit(definition); c.state.fields.valueType = 'multi_select'; c.state.fields.optionsText = '红色\n蓝色'
  await c.state.save(); c.state.editing.value.id = 'other'; c.state.fields.optionsText = '黑色'; await c.state.save()
  assert.equal(calls[1][0], '5'); assert.equal(calls[1][1].options.join(','), '红色,蓝色')
  assert.equal(calls[0][2], calls[1][2]); assert.equal('propertyKey' in calls[1][1], false)
  assert.equal(definition.id, '5'); c.close()
})

test('明确拒绝保留输入可修正，处理中继续锁定', async () => {
  for (const code of ['PROPERTY_CONFLICT', 'IDEMPOTENCY_IN_PROGRESS']) {
    const c = await setup({ createProperty: async () => { throw new ApiError('拒绝', 601, code) } })
    c.state.fields.name = '输入'; await c.state.save()
    assert.equal(c.state.uncertain.value, code === 'IDEMPOTENCY_IN_PROGRESS')
    assert.equal(c.state.fields.name, '输入'); c.close()
  }
})

test('校验期间切账号不提交，旧写回不触发刷新或成功回调', async () => {
  let resolve
  const c = await setup(); c.state.form.value.validate = () => new Promise(done => { resolve = done })
  const pending = c.state.save(); c.auth.token = 'two'; resolve(true); await pending
  assert.equal(c.calls.length, 0); assert.equal(c.state.editable.value, false); c.close()
  const d = await setup({ createProperty: () => new Promise(done => { resolve = done }) })
  d.state.fields.name = '旧账号'; const saving = d.state.save(); await tick(); d.auth.token = 'two'
  resolve({ data: definition }); await saving
  assert.equal(d.changed(), 0); assert.equal(d.state.rows.value.length, 0); assert.equal(d.state.fields.name, '')
  assert.equal(await d.state.confirmDiscard(), true); d.close()
})

test('缓存隐藏后的旧请求不解锁返回后的原请求重试', async () => {
  const resolvers = [], calls = []
  const c = await setup({ createProperty: (...args) => { calls.push(args); return new Promise(done => resolvers.push(done)) } })
  c.state.fields.name = '属性'; const first = c.state.save(); await tick()
  c.hooks.deactivate(); c.hooks.activate(); const second = c.state.save(); await tick()
  assert.equal(calls[0][2], calls[1][2])
  resolvers[0]({ data: definition }); await first; assert.equal(c.state.saving.value, true)
  resolvers[1]({ data: definition }); await second; assert.equal(c.changed(), 1); c.close()
})

test('切换项目保护未保存配置，迟到确认不得覆盖新生命周期', async () => {
  let resolve
  const c = await setup({}, () => new Promise(done => { resolve = done }))
  c.state.fields.name = '保留'
  const pending = c.state.edit(definition); c.hooks.deactivate(); c.hooks.activate(); resolve(); await pending
  assert.equal(c.state.fields.name, '保留')
  assert.equal(c.hooks.update({ params: { id: '99' } }, { params: { id: '99' } }), true)
  const leave = c.hooks.update({ params: { id: '100' } }, { params: { id: '99' } }); resolve(); assert.equal(await leave, true)
  c.close()
})

test('属性页签隐藏保留草稿、取消读取和旧校验，缓存恢复不能越过隐藏状态',async()=>{
 const reads=[]
 const c=await setup({listProperties:(...args)=>new Promise(resolve=>reads.push({args,resolve}))})
 c.state.fields.name='待保存属性';let validate
 c.state.form.value={validate:()=>new Promise(resolve=>{validate=resolve})}
 const save=c.state.save();c.visible.value=false
 assert.equal(c.state.active.value,false);assert.equal(reads[0].args[2].aborted,true)
 c.visible.value=true;validate(true);await save
 assert.equal(c.calls.length,0);assert.equal(c.state.fields.name,'待保存属性');assert.equal(reads.length,2)
 c.visible.value=false;c.hooks.deactivate();c.visible.value=true
 assert.equal(reads.length,2);c.hooks.activate();assert.equal(reads.length,3)
 reads[0].resolve({rows:[{id:'stale'}],total:1});await tick();assert.equal(c.state.rows.value.length,0)
 c.close()
})
