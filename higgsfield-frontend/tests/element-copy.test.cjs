const { test } = require('node:test'),
  assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'),
  { join } = require('node:path'),
  { runInNewContext } = require('node:vm')
const ts = require('typescript'),
  vue = require('vue')
const tick = () => new Promise(setImmediate)
function setup(confirm = async () => { throw new Error('取消') }, projectReader) {
  const exports = {},
    auth = vue.reactive({ token: 'one', user: { permissions: [] } }),
    calls = [],
    reads = [],
    visible = vue.ref(true),
    hooks = {}
  let key = 0
  const source = {
    element: { id: '9007199254740993', projectId: '99', name: '主角' },
    currentRevision: { id: '901', media: [{ assetVersionId: '11' }] },
  }
  class ApiError extends Error {
    constructor(message, code, errorCode) {
      super(message)
      this.code = code
      this.errorCode = errorCode
    }
  }
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/useElementCopy.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS } },
    ).outputText,
    {
      exports,
      Error,
      AbortController,
      crypto: { randomUUID: () => String(++key) },
      require(id) {
        if (id === 'vue')
          return {
            ...vue,
            onBeforeUnmount: (fn) => {
              hooks.close = fn
            },
            onActivated: (fn) => {
              hooks.activate = fn
            },
            onDeactivated: (fn) => {
              hooks.deactivate = fn
            },
          }
        if (id === 'vue-router')
          return {
            onBeforeRouteLeave: (fn) => {
              hooks.leave = fn
            },
            onBeforeRouteUpdate: (fn) => {
              hooks.update = fn
            },
          }
        if (id.includes('stores/auth')) return { useAuthStore: () => auth }
        if (id.includes('client')) return { ApiError }
        if (id === 'element-plus') return { ElMessageBox: { confirm } }
        return {
          copyElement: (...args) =>
            new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
          getProjects: projectReader || (async () => ({
            rows: [
              { id: '99', name: '原项目' },
              { id: '100', name: '目标项目' },
            ],
            total: 2,
          })),
          readBrief: async (id, signal) => {
            reads.push({ id, signal })
            return { data: { allowedActions: ['element:create', 'asset:create'] } }
          },
        }
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() => exports.useElementCopy(source, () => visible.value))
  state.form.value = { validate: async () => true }
  state.fields.alias = 'new-hero'
  return {
    visible,
    state,
    source,
    auth,
    calls,
    reads,
    hooks,
    ApiError,
    close() {
      hooks.close()
      scope.stop()
    },
  }
}

test('复制结果未知冻结原目标、修订与键，成功前禁止关闭和新请求', async () => {
  const h = setup()
  await tick()
  h.state.fields.targetProjectId = '100'
  await tick()
  const run = h.state.submit()
  await tick()
  h.source.currentRevision.id = '999'
  h.calls[0].reject(new Error('断网'))
  await run
  assert.equal(h.state.locked.value, true)
  assert.equal(await h.hooks.leave(), false)
  assert.equal(await h.hooks.update({ fullPath: '/p?tab=x' }, { fullPath: '/p?tab=y' }), false)
  h.state.fields.name = '另一个名称'
  const retry = h.state.submit()
  await tick()
  assert.equal(h.calls[1].args[0], '9007199254740993')
  assert.equal(h.calls[1].args[1].sourceRevisionId, '901')
  assert.equal(h.calls[1].args[1].name, '主角')
  assert.equal(h.calls[1].args[1].targetProjectId, '100')
  assert.equal(h.calls[1].args[2], h.calls[0].args[2])
  h.calls[1].resolve({ data: { id: 'new' } })
  await retry
  assert.equal(h.state.result.value.id, 'new')
  assert.equal(h.state.locked.value, false)
  await h.state.submit()
  assert.equal(h.calls.length, 2)
  h.close()
})

test('复制校验期间切换账号或修改字段不提交，迟到成功不回填新会话', async () => {
  const h = setup()
  await tick()
  let valid
  h.state.form.value = {
    validate: () =>
      new Promise((resolve) => {
        valid = resolve
      }),
  }
  const run = h.state.submit()
  h.auth.token = 'two'
  valid(true)
  await run
  assert.equal(h.calls.length, 0)
  assert.equal(h.state.fields.name, '')
  h.state.fields.targetProjectId = '100'
  h.state.fields.name = '新名'
  await tick()
  const changed = h.state.submit()
  h.state.fields.alias = 'changed'
  valid(true)
  await changed
  assert.equal(h.calls.length, 0)
  h.state.form.value = { validate: async () => true }
  const late = h.state.submit()
  await tick()
  h.auth.token = 'three'
  h.calls[0].resolve({ data: { id: 'old' } })
  await late
  assert.equal(h.state.result.value, undefined)
  assert.equal(h.state.saving.value, false)
  h.close()
})

test('复制缓存停用不发新请求，恢复后校验原目标并用原键重试', async () => {
  const h = setup()
  await tick()
  const run = h.state.submit()
  await tick()
  h.hooks.deactivate()
  h.calls[0].reject(new Error('断网'))
  await run
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  assert.equal(h.state.active.value, false)
  h.hooks.activate()
  await tick()
  assert.equal(h.reads.at(-1).id, '99')
  const retry = h.state.submit()
  await tick()
  assert.equal(h.calls[1].args[2], h.calls[0].args[2])
  h.calls[1].resolve({ data: { id: 'new' } })
  await retry
  h.close()
})

test('明确别名冲突解锁修改，下次新内容使用新幂等键', async () => {
  const h = setup()
  await tick()
  const run = h.state.submit()
  await tick()
  h.calls[0].reject(new h.ApiError('别名冲突', 601, 'ALIAS_CONFLICT'))
  await run
  assert.equal(h.state.uncertain.value, false)
  assert.equal(await h.hooks.leave(), false)
  h.state.fields.alias = 'another'
  const retry = h.state.submit()
  await tick()
  assert.notEqual(h.calls[1].args[2], h.calls[0].args[2])
  assert.equal(h.calls[1].args[1].alias, 'another')
  h.calls[1].resolve({ data: { id: 'new' } })
  await retry
  h.close()
})


test('复制配置关闭确认取消保留字段，成功结果不再提示未保存', async () => {
  const h = setup(); await tick()
  h.state.fields.name = '复制的新名称'
  assert.equal(await h.state.confirmClose(), false)
  assert.equal(h.state.fields.name, '复制的新名称')
  const pending = h.state.submit(); await tick()
  h.calls[0].resolve({ data: { id: 'new', name: '复制的新名称', projectId: '99' } }); await pending
  assert.equal(await h.state.confirmClose(), true); h.close()
})

test('复制配置迟到关闭确认不影响隐藏返回的页面或正在提交的请求', async () => {
  let resolve
  const h = setup(() => new Promise(done => { resolve = done })); await tick()
  const previous = h.state.confirmClose(); h.hooks.deactivate(); h.hooks.activate(); resolve()
  assert.equal(await previous, false); await tick()
  const current = h.state.confirmClose(); const saving = h.state.submit(); await tick(); resolve()
  assert.equal(await current, false)
  h.calls[0].resolve({ data: { id: 'new', projectId: '99' } }); await saving
  assert.equal(await h.state.confirmClose(), true); h.close()
})

test('单项复制页签显隐保留配置并隔离旧校验，缓存停用时不恢复',async()=>{
 const h=setup();await tick();h.state.fields.targetProjectId='100';h.state.fields.name='保留名称';await tick()
 let validate;h.state.form.value={validate:()=>new Promise(resolve=>{validate=resolve})}
 const save=h.state.submit();h.visible.value=false
 assert.equal(h.state.active.value,false);assert.equal(h.state.eligible.value,false)
 h.visible.value=true;await tick();validate(true);await save
 assert.equal(h.calls.length,0);assert.equal(h.state.fields.name,'保留名称');assert.equal(h.state.fields.alias,'new-hero')
 h.hooks.deactivate();h.visible.value=false;h.visible.value=true;assert.equal(h.state.active.value,false)
 h.hooks.activate();await tick();assert.equal(h.state.eligible.value,true)
 assert.equal(h.state.fields.targetProjectId,'100');h.close()
})


test('权限变化取消旧项目查询并清空候选，迟到响应不可恢复',async()=>{
 const queries=[];const h=setup(undefined,(...args)=>new Promise(resolve=>queries.push({args,resolve})))
 h.auth.user.permissions=['changed'];assert.equal(queries[0].args[1].aborted,true)
 queries[1].resolve({rows:[{id:'new',name:'新授权'}],total:1});await tick()
 queries[0].resolve({rows:[{id:'private',name:'旧授权'}],total:1});await tick()
 assert.equal(h.state.projects.value[0].id,'new');assert.equal(h.state.total.value,1);h.close()
})
