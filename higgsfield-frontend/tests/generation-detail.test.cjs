const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

const flush = async () => { await vue.nextTick(); await new Promise(resolve => setImmediate(resolve)) }

test('旧快照与重置不能回退终态或重连游标，同版本撤权仍应用', async () => {
  const h = harness()
  const latest = { id: '1', revision: '9007199254740994', eventCursor: '1:9007199254740995', orchestrationState: 'finished', outputs: [], billingVisibility: 'visible', billing: { platform: { amount: '5', currency: 'CNY' } } }
  h.calls[0].resolve({ data: latest })
  await flush()
  for (const event of ['task.snapshot', 'stream.reset']) {
    for (const old of [
      { ...latest, revision: '9007199254740993', orchestrationState: 'running' },
      { ...latest, eventCursor: '1:9007199254740994', orchestrationState: 'running' },
    ]) {
      await h.streams[0][3]({ event, data: JSON.stringify(event === 'stream.reset' ? { snapshot: old } : old) })
      assert.equal(h.state.detail.value.orchestrationState, 'finished')
    }
  }
  await h.streams[0][3]({ event: 'task.snapshot', data: JSON.stringify({ ...latest, billingVisibility: 'hidden', billing: undefined }) })
  assert.equal(h.state.detail.value.billing, undefined)
  h.streams[0].reject(new Error('断线'))
  await flush()
  h.timers[0].fn()
  assert.equal(h.streams[1][1], latest.eventCursor)
  h.cleanup()
})

test('普通事件迟到读取不回退游标，错误任务身份不能覆盖当前详情', async () => {
  const h = harness()
  const latest = { id: '1', revision: '5', eventCursor: '1:10', outputs: [] }
  h.calls[0].resolve({ data: latest })
  await flush()
  const applied = h.streams[0][3]({ event: 'task.state', id: '1:11', data: '{}' })
  h.calls[1].resolve({ data: { ...latest, revision: '4', eventCursor: '1:9' } })
  await applied
  assert.equal(h.state.detail.value.revision, '5')
  await assert.rejects(h.streams[0][3]({ event: 'task.snapshot', data: JSON.stringify({ ...latest, id: '2' }) }), /身份/)
  await assert.rejects(h.streams[0][3]({ event: 'stream.reset', data: JSON.stringify({ snapshot: { ...latest, eventCursor: '2:11' } }) }), /游标/)
  h.streams[0].reject(new Error('断线'))
  await flush()
  h.timers[0].fn()
  assert.equal(h.streams[1][1], '1:10')
  h.cleanup()
})

test('费用权限重置在相同任务版本下清除旧金额', async () => {
  const h = harness()
  h.calls[0].resolve({ data: { id: '1', revision: '1', eventCursor: '1:7', outputs: [], billingVisibility: 'visible', billing: { platform: { amount: '12.393', currency: 'CNY' } } } })
  await flush()
  assert.equal(h.state.detail.value.billing.platform.amount, '12.393')
  await h.streams[0][3]({ event: 'stream.reset', data: JSON.stringify({ snapshot: { id: '1', revision: '1', eventCursor: '1:7', outputs: [], billingVisibility: 'hidden' } }) })
  assert.equal(h.state.detail.value.billingVisibility, 'hidden')
  assert.equal(h.state.detail.value.billing, undefined)
  h.cleanup()
})
function harness() {
  const auth = vue.reactive({ token: 'one', user: { permissions: [] } })
  const exports = {}, calls = [], revoked = [], hooks = {}, streams = [], timers = [], identity = vue.ref('1')
  const source = readFileSync(require('node:path').join(__dirname, '../src/composables/useGenerationDetail.ts'), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const pending = (type, ...args) => new Promise(resolve => calls.push({ type, args, resolve }))
  runInNewContext(compiled, { exports, AbortController, setTimeout: (fn, delay) => { const timer = { fn, delay, cancelled: false }; timers.push(timer); return timer }, clearTimeout: timer => { timer.cancelled = true }, URL: { createObjectURL: () => 'blob:preview', revokeObjectURL: value => revoked.push(value) },
    require: name => name.includes('stores/auth') ? { useAuthStore: () => auth } : name === 'vue' ? { ...vue, onBeforeUnmount: fn => { hooks.unmount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn } } : {
      getGeneration: (...args) => pending('detail', ...args), getGenerationInput: (...args) => pending('input', ...args), getOutputMedia: (...args) => pending('media', ...args),
      subscribeGeneration: (...args) => { streams.push(args); args[4](); return new Promise((_, reject) => { args.reject = reject }) },
    } })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useGenerationDetail(() => identity.value))
  return { state, auth, hooks, identity, calls, revoked, streams, timers, cleanup() { hooks.unmount(); scope.stop() } }
}
test('切换详情隔离迟到响应，关闭时释放媒体地址与请求', async () => {
  const h = harness()
  h.identity.value = '2'
  await flush()
  h.calls[1].resolve({ data: { id: '2', kind: 'image', outputs: [{ id: '8', kind: 'image', previewUrl: '/preview' }] } })
  await flush()
  h.calls[0].resolve({ data: { id: '1' } })
  await flush()
  assert.equal(h.state.detail.value.id, '2')
  const media = h.state.media(h.state.detail.value.outputs[0])
  h.calls[2].resolve(new Blob(['image']))
  await media
  assert.equal(h.state.mediaUrl.value, 'blob:preview')
  const input = h.state.readInput()
  h.identity.value = undefined
  await flush()
  assert.deepEqual(h.revoked, ['blob:preview'])
  assert.equal(h.calls[3].args[1].aborted, true)
  h.calls[3].resolve({ data: { prompt: 'old' } })
  await input
  assert.equal(h.state.input.value, undefined)
  assert.equal(h.state.detail.value, undefined)
  h.cleanup()
})

test('未授权下载或不属于当前任务的输出不发请求', async () => {
  const h = harness()
  const output = { id: '8', kind: 'image', previewUrl: '/preview' }
  h.calls[0].resolve({ data: { id: '1', kind: 'image', outputs: [output] } })
  await flush()
  await h.state.media(output, true)
  await h.state.media({ ...output, id: '9' })
  assert.equal(h.calls.length, 1)
  h.cleanup()
})

test('流撤权停止连接并清理已显示内容，不自动重连', async () => {
  const h = harness()
  h.calls[0].resolve({ data: { id: '1', kind: 'image', revision: '1', eventCursor: '1:0', outputs: [] } })
  await flush()
  assert.equal(h.state.liveState.value, 'live')
  assert.equal(h.streams[0][1], '1:0')
  await h.streams[0][3]({ event: 'access.revoked', data: '{"reason":"permission_changed"}' })
  assert.equal(h.streams[0][2].aborted, true)
  assert.equal(h.state.detail.value, undefined)
  assert.equal(h.state.liveState.value, 'stopped')
  assert.match(h.state.error.value, /权限/)
  h.cleanup()
})

test('已应用事件去重，重连使用处理成功后的快照游标并取消待重连定时器', async () => {
  const h = harness()
  h.calls[0].resolve({ data: { id: '1', revision: '1', eventCursor: '1:7', outputs: [] } })
  await flush()
  await h.streams[0][3]({ event: 'task.state', id: '1:7', data: '{}' })
  assert.equal(h.calls.length, 1)
  const applied = h.streams[0][3]({ event: 'task.state', id: '1:8', data: '{}' })
  h.calls[1].resolve({ data: { id: '1', revision: '2', eventCursor: '1:8', outputs: [] } })
  await applied
  h.streams[0].reject(new Error('断线'))
  await flush()
  assert.equal(h.timers[0].delay, 3000)
  h.timers[0].fn()
  assert.equal(h.streams[1][1], '1:8')
  h.streams[1].reject(new Error('再次断线'))
  await flush()
  h.cleanup()
  assert.equal(h.timers.at(-1).cancelled, true)
  assert.equal(h.streams[1][2].aborted, true)
})

test('归档事件重新读取任务修订与操作权限，不把输出修订当任务修订', async () => {
  const h = harness()
  h.calls[0].resolve({ data: { id: '1', revision: '8', eventCursor: '1:10', outputsVisibility: 'visible', outputs: [{ id: '20', revision: '3', archiveState: 'archive_failed', allowedActions: ['output:archive'] }] } })
  await flush()
  const applied = h.streams[0][3]({ event: 'output.state', id: '1:11', data: JSON.stringify({ payload: { outputId: '20', revision: '4', archiveState: 'not_started' } }) })
  assert.equal(h.state.detail.value.revision, '8')
  h.calls[1].resolve({ data: { id: '1', revision: '9', eventCursor: '1:11', outputsVisibility: 'visible', outputs: [{ id: '20', revision: '4', archiveState: 'not_started', allowedActions: [] }] } })
  await applied
  assert.equal(h.state.detail.value.revision, '9')
  assert.equal(h.state.detail.value.outputs[0].revision, '4')
  assert.equal(h.state.detail.value.outputs[0].allowedActions.length, 0)
  h.cleanup()
})


test('任务目标从服务器恢复，权限和账号变化清除旧目标，缓存恢复重新读取', async () => {
 const h=harness();const target={id:'9007199254740993',projectId:'99',name:'主角'}
 h.calls[0].resolve({data:{id:'1',revision:'1',outputs:[],elementDestination:target}});await flush()
 assert.equal(h.state.detail.value.elementDestination.id,target.id)
 h.auth.user.permissions=['changed'];assert.equal(h.state.detail.value,undefined)
 h.calls[1].resolve({data:{id:'1',revision:'1',outputs:[],elementDestination:null}});await flush();assert.equal(h.state.detail.value.elementDestination,null)
 h.hooks.deactivate();assert.equal(h.state.detail.value,undefined);await h.state.refresh();assert.equal(h.calls.length,2)
 h.hooks.activate();h.auth.token='two';h.calls[2].resolve({data:{id:'1',elementDestination:target}});await flush();assert.equal(h.state.detail.value,undefined)
 h.calls[3].resolve({data:{id:'1',revision:'1',outputs:[],elementDestination:null}});await flush();assert.equal(h.state.detail.value.elementDestination,null);h.cleanup()
})

test('同版本权限快照清除来源入口，切换任务不保留旧来源', async () => {
  const h = harness()
  h.calls[0].resolve({ data: { id: '1', revision: '1', eventCursor: '1:7', outputs: [], sourceJobId: '9007199254740993' } })
  await flush()
  assert.equal(h.state.detail.value.sourceJobId, '9007199254740993')
  await h.streams[0][3]({ event: 'task.snapshot', id: '1:7', data: JSON.stringify({ id: '1', revision: '1', eventCursor: '1:7', outputs: [], sourceJobId: null }) })
  assert.equal(h.state.detail.value.sourceJobId, null)
  h.identity.value = '2'
  await flush()
  assert.equal(h.state.detail.value, undefined)
  h.cleanup()
})

test('普通事件移除输出时释放预览并阻止旧输出对象再次请求', async () => {
  const h = harness()
  const output = { id: '8', revision: '1', kind: 'image', previewUrl: '/preview', downloadUrl: '/download' }
  h.calls[0].resolve({ data: { id: '1', revision: '1', eventCursor: '1:7', outputsVisibility: 'visible', outputs: [output] } })
  await flush()
  const preview = h.state.media(output)
  h.calls[1].resolve(new Blob(['image']))
  await preview
  const applied = h.streams[0][3]({ event: 'output.state', id: '1:8', data: '{}' })
  h.calls[2].resolve({ data: { id: '1', revision: '2', eventCursor: '1:8', outputsVisibility: 'visible', outputs: [] } })
  await applied
  assert.equal(h.state.mediaUrl.value, '')
  assert.deepEqual(h.revoked, ['blob:preview'])
  await h.state.media(output)
  assert.equal(h.calls.length, 3)
  h.cleanup()
})

test('媒体权限刷新取消在途预览，旧对象不能绕过当前下载权限', async () => {
  const h = harness()
  const output = { id: '8', revision: '1', kind: 'image', previewUrl: '/preview', downloadUrl: '/download' }
  h.calls[0].resolve({ data: { id: '1', revision: '1', eventCursor: '1:7', outputsVisibility: 'visible', outputs: [output] } })
  await flush()
  const preview = h.state.media(output)
  const applied = h.streams[0][3]({ event: 'output.state', id: '1:8', data: '{}' })
  h.calls[2].resolve({ data: { id: '1', revision: '2', eventCursor: '1:8', outputsVisibility: 'visible', outputs: [{ ...output, previewUrl: undefined, downloadUrl: undefined }] } })
  await applied
  assert.equal(h.calls[1].args[2].aborted, true)
  h.calls[1].resolve(new Blob(['late']))
  await preview
  assert.equal(h.state.mediaUrl.value, '')
  assert.equal(h.state.mediaLoading.value, false)
  await h.state.media(output, true)
  assert.equal(h.calls.length, 3)
  // 仍可预览但不可下载时，旧对象的下载地址也不能作为授权依据。
  h.state.detail.value.outputs[0].previewUrl = '/preview'
  await h.state.media(output, true)
  assert.equal(h.calls.length, 3)
  h.cleanup()
})

test('断线期间撤权后相同游标快照清除旧输入媒体及操作入口', async () => {
  const h = harness()
  const output = { id: '8', revision: '1', kind: 'image', previewUrl: '/preview', downloadUrl: '/download' }
  h.calls[0].resolve({ data: { id: '1', kind: 'image', revision: '1', eventCursor: '1:7', outputsVisibility: 'visible', outputs: [output], allowedActions: ['generation:cancel'], elementDestination: { id: '9', projectId: '2', name: '旧目标' } } })
  await flush()
  const preview = h.state.media(output)
  h.calls[1].resolve(new Blob(['image']))
  await preview
  const input = h.state.readInput()
  h.calls[2].resolve({ data: { prompt: '旧输入' } })
  await input
  h.streams[0].reject(new Error('断线'))
  await flush()
  h.timers[0].fn()
  assert.equal(h.streams[1][1], '1:7')
  await h.streams[1][3]({ event: 'task.snapshot', id: '1:7', data: JSON.stringify({ id: '1', kind: 'image', revision: '1', eventCursor: '1:7', outputsVisibility: 'hidden', outputs: [], allowedActions: [], elementDestination: null }) })
  assert.equal(h.state.input.value, undefined)
  assert.equal(h.state.mediaUrl.value, '')
  assert.deepEqual(h.revoked, ['blob:preview'])
  assert.equal(h.state.detail.value.allowedActions.length, 0)
  assert.equal(h.state.detail.value.elementDestination, null)
  assert.equal(h.state.liveState.value, 'live')
  h.cleanup()
})
