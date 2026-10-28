const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'),
  { join } = require('node:path'),
  { runInNewContext } = require('node:vm')
const ts = require('typescript'),
  vue = require('vue')
const tick = () => new Promise(setImmediate)
function setup(confirm = async () => { throw new Error('取消') }, projectReader) {
  const exports = {},
    auth = vue.reactive({ token: 'one', user: { permissions: [] } }),
    permitted = vue.ref(true),
    visible = vue.ref(true),
    hooks = {},
    calls = [],
    changed = []
  let key = 0
  class ApiError extends Error {
    constructor(message, code, errorCode) {
      super(message)
      this.code = code
      this.errorCode = errorCode
    }
  }
  const sources = ['1', '2'].map((id) => ({
    id,
    projectId: '99',
    name: `元素${id}`,
    currentRevisionId: `90${id}`,
    allowedActions: ['element:copy'],
  }))
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/useElementBatchCopy.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
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
          readElement: async (id) => ({
            data: {
              element: sources.find((item) => item.id === id),
              currentRevision: { id: `90${id}`, media: [{ assetVersionId: '11' }] },
            },
          }),
          getProjects: projectReader || (async () => ({
            rows: [
              { id: '99', name: '原项目' },
              { id: '100', name: '目标项目' },
            ],
            total: 2,
          })),
          readBrief: async () => ({ data: { allowedActions: ['element:create', 'asset:create'] } }),
        }
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() =>
      exports.useElementBatchCopy(
        () => permitted.value,
        (ids) => changed.push([...ids]),
        () => visible.value,
      ),
    )
  state.form.value = { validate: async () => true }
  async function open() {
    await state.open([...sources, sources[0], { id: '3', allowedActions: [] }])
    await tick()
    state.fields.items.forEach((item) => {
      item.alias = `copy-${item.id}`
    })
  }
  return {
    state,
    visible,
    sources,
    auth,
    permitted,
    hooks,
    calls,
    changed,
    ApiError,
    open,
    close() {
      hooks.close()
      scope.stop()
    },
  }
}
test('批量复制去重排除无权项，部分成功后仅以原目标修订和键重试未知项', async () => {
  const h = setup()
  await h.open()
  assert.equal(h.state.fields.items.length, 2)
  h.state.fields.targetProjectId = '100'
  await tick()
  const run = h.state.submit()
  await tick()
  h.calls[0].resolve({ data: { id: '101', name: '新1' } })
  await tick()
  h.calls[1].reject(new Error('断网'))
  await run
  assert.deepEqual(h.changed, [['1']])
  assert.equal(h.state.locked.value, true)
  assert.equal(await h.hooks.leave(), false)
  await h.state.close()
  assert.equal(h.state.opened.value, true)
  h.sources[1].currentRevisionId = '999'
  h.state.fields.items[1].name = '被程序修改'
  const retry = h.state.submit()
  await tick()
  assert.equal(h.calls[2].args[0], '2')
  assert.equal(h.calls[2].args[1].sourceRevisionId, '902')
  assert.equal(h.calls[2].args[1].targetProjectId, '100')
  assert.equal(h.calls[2].args[1].name, 'Copy of 元素2')
  assert.equal(h.calls[2].args[2], h.calls[1].args[2])
  h.calls[2].resolve({ data: { id: '102' } })
  await retry
  assert.equal(h.state.remaining.value.length, 0)
  assert.equal(h.state.locked.value, false)
  await h.state.submit()
  assert.equal(h.calls.length, 3)
  h.close()
})
test('明确冲突释放该项意图，修正别名后新键重试；批内重复别名拒绝写入', async () => {
  const h = setup()
  await h.open()
  h.state.fields.items[1].alias = 'copy-1'
  await h.state.submit()
  assert.equal(h.calls.length, 0)
  h.state.fields.items[1].alias = 'copy-2'
  const run = h.state.submit()
  await tick()
  h.calls[0].reject(new h.ApiError('冲突', 601, 'ALIAS_CONFLICT'))
  await tick()
  h.calls[1].resolve({ data: { id: '102' } })
  await run
  assert.equal(h.state.locked.value, false)
  h.state.fields.items[0].alias = 'new'
  const retry = h.state.submit()
  await tick()
  assert.notEqual(h.calls[2].args[2], h.calls[0].args[2])
  assert.equal(h.calls[2].args[1].alias, 'new')
  h.calls[2].resolve({ data: { id: '101' } })
  await retry
  h.close()
})
test('缓存停用停止后续写入，激活后只刷新已成功项并恢复固定请求', async () => {
  const h = setup()
  await h.open()
  const run = h.state.submit()
  await tick()
  h.hooks.deactivate()
  h.calls[0].resolve({ data: { id: '101' } })
  await run
  assert.equal(h.calls.length, 1)
  assert.deepEqual(h.changed, [])
  assert.equal(h.state.locked.value, true)
  h.hooks.activate()
  await tick()
  assert.deepEqual(h.changed, [['1']])
  const retry = h.state.submit()
  await tick()
  assert.equal(h.calls[1].args[0], '2')
  h.calls[1].resolve({ data: { id: '102' } })
  await retry
  h.close()
})
test('异步校验遇账号切换不写入，迟到成功不污染新账号；撤权停止后续项', async () => {
  const h = setup()
  await h.open()
  let validate
  h.state.form.value = {
    validate: () =>
      new Promise((resolve) => {
        validate = resolve
      }),
  }
  const run = h.state.submit()
  h.auth.token = 'two'
  validate(true)
  await run
  assert.equal(h.calls.length, 0)
  await h.open()
  h.state.form.value = { validate: async () => true }
  const late = h.state.submit()
  await tick()
  h.auth.token = 'three'
  h.calls[0].resolve({ data: { id: '101' } })
  await late
  assert.deepEqual(h.changed, [])
  assert.equal(h.state.fields.items.length, 0)
  await h.open()
  const revoked = h.state.submit()
  await tick()
  h.permitted.value = false
  h.calls[1].resolve({ data: { id: '101' } })
  await revoked
  assert.equal(h.calls.length, 2)
  assert.equal(h.state.eligible.value, false)
  h.close()
})

test('批量复制取消关闭保留配置，确认关闭保留已成功条目', async () => {
  let accept = false
  const h = setup(async () => { if (!accept) throw new Error('取消') }); await h.open()
  await h.state.close(); assert.equal(h.state.opened.value, true)
  assert.equal(h.state.fields.items[0].alias, 'copy-1')
  const run = h.state.submit(); await tick()
  h.calls[0].resolve({ data: { id: '101' } }); await tick()
  h.calls[1].reject(new h.ApiError('别名重复', 601, 'ALIAS_CONFLICT')); await run
  assert.equal(h.state.remaining.value.length, 1); assert.equal(h.state.locked.value, false)
  await h.state.close(); assert.equal(h.state.opened.value, true)
  accept = true; await h.state.close()
  assert.equal(h.state.opened.value, false); assert.deepEqual(h.changed, [['1']]); h.close()
})

test('批量复制迟到确认不关闭返回页面，全部成功后直接关闭', async () => {
  let resolve
  const h = setup(() => new Promise(done => { resolve = done })); await h.open()
  const closing = h.state.close(); h.hooks.deactivate(); h.hooks.activate(); resolve(); await closing
  assert.equal(h.state.opened.value, true); await tick()
  const run = h.state.submit(); await tick()
  h.calls[0].resolve({ data: { id: '101' } }); await tick()
  h.calls[1].resolve({ data: { id: '102' } }); await run
  assert.equal(h.state.dirty.value, false)
  await h.state.close(); assert.equal(h.state.opened.value, false); h.close()
})

test('复制页签隐藏保留配置并暂停剩余项，返回重新鉴权后继续原批次',async()=>{
 const h=setup();await h.open();h.state.fields.targetProjectId='100';await tick()
 const run=h.state.submit();await tick();assert.equal(h.calls.length,1)
 h.visible.value=false;assert.equal(h.state.active.value,false)
 h.calls[0].resolve({data:{id:'101',name:'复制一'}});await run
 assert.equal(h.calls.length,1);assert.equal(h.changed.length,0)
 assert.equal(h.state.fields.targetProjectId,'100');assert.equal(h.state.fields.items[1].alias,'copy-2')
 h.hooks.deactivate();h.visible.value=true;assert.equal(h.state.active.value,false)
 h.hooks.activate();await tick();assert.equal(h.changed.length,1)
 const retry=h.state.submit();await tick();assert.equal(h.calls.length,2)
 assert.equal(h.calls[1].args[0],'2');assert.equal(h.calls[1].args[1].targetProjectId,'100')
 assert.equal(h.calls[1].args[1].sourceRevisionId,'902')
 h.calls[1].resolve({data:{id:'102',name:'复制二'}});await retry
 assert.equal(h.changed.length,2);h.close()
})


test('批量复制失权清空目标候选且旧查询不能回填',async()=>{
 const queries=[];const h=setup(undefined,(...args)=>new Promise(resolve=>queries.push({args,resolve})))
 await h.state.open(h.sources);await tick();h.permitted.value=false
 assert.equal(queries[0].args[1].aborted,true);assert.equal(h.state.projects.value.length,0)
 queries[0].resolve({rows:[{id:'private'}],total:1});await tick()
 assert.equal(h.state.projects.value.length,0);assert.equal(h.state.total.value,0);assert.equal(queries.length,1);h.close()
})
