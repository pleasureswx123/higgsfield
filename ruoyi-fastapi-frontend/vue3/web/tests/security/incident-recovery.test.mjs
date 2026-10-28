import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { webcrypto } from 'node:crypto'

test('归档恢复保留修订和重试键，撤权忽略迟到写响应', async () => {
  const calls = [], hooks = {}, user = reactive({ token: 'session-one', id: '1', permissions: ['operations:read', 'operations:recover'] })
  let refreshes = 0
  const context = createContext({ crypto: webcrypto, AbortController })
  const mocks = {
    vue: { computed, reactive, ref, watch, onDeactivated: () => {}, onBeforeUnmount: () => {} },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/incidents': { recoverIncident: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useIncidentRecovery.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useIncidentRecovery(() => { refreshes++ }))
  const flush = () => new Promise(resolve => setImmediate(resolve))
  state.start({ jobId: '1', revision: '7', allowedActions: [] })
  assert.equal(state.target.value, undefined)
  const row = { jobId: '9007199254740993', revision: '7', allowedActions: ['retry_archive'] }
  state.start(row)
  row.revision = '8'
  state.form.reason = '修复归档网络'
  state.form.evidenceRef = 'ticket:123'
  state.formRef.value = { validate: async () => true }
  const first = state.submit()
  await flush()
  assert.equal(calls[0].args[1].revision, '7')
  assert.equal(hooks.leave(), false)
  calls[0].reject(new Error('响应丢失'))
  await first
  assert.equal(state.uncertain.value, true)
  assert.equal(hooks.leave(), false)
  state.close()
  assert.equal(state.target.value.jobId, row.jobId)
  state.start({ jobId: '2', revision: '1', allowedActions: ['requery'] }, 'requery')
  assert.equal(state.target.value.jobId, row.jobId)
  state.form.reason = '不能改变已发送的原因'
  const retry = state.submit()
  await flush()
  assert.equal(calls[1].args[2], calls[0].args[2])
  assert.equal(calls[1].args[1].reason, '修复归档网络')
  user.permissions = ['operations:read']
  calls[1].resolve({})
  await retry
  assert.equal(state.target.value, undefined)
  assert.equal(state.pending.value, false)
  assert.equal(state.uncertain.value, false)
  assert.equal(refreshes, 0)
  user.permissions = ['operations:read', 'operations:recover']
  state.start({ ...row, allowedActions: ['requery'] }, 'requery')
  state.form.reason = '核查现有任务'
  const query = state.submit()
  await flush()
  assert.equal(calls[2].args[1].action, 'requery')
  calls[2].resolve({})
  await query
  assert.equal(refreshes, 1)
  state.start({ ...row, allowedActions: ['close_tracking'] }, 'close_tracking')
  state.form.reason = '人工接管'
  await state.submit()
  assert.equal(calls.length, 3)
  assert.match(state.error.value, /证据引用/)
  state.form.evidenceRef = 'ticket:456'
  const closing = state.submit()
  await flush()
  assert.equal(calls[3].args[1].action, 'close_tracking')
  assert.equal(calls[3].args[1].evidenceRef, 'ticket:456')
  calls[3].resolve({})
  await closing
  assert.equal(refreshes, 2)
  state.start({ ...row, allowedActions: ['confirm_not_accepted'] }, 'confirm_not_accepted')
  state.form.reason = '核对拒绝证据'
  state.form.evidenceRef = 'ticket:123'
  await state.submit()
  assert.equal(calls.length, 4)
  assert.match(state.error.value, /provider-call/)
  state.form.evidenceRef = 'provider-call:9'
  const confirmation = state.submit()
  await flush()
  assert.equal(calls[4].args[1].action, 'confirm_not_accepted')
  calls[4].resolve({})
  await confirmation
  assert.equal(refreshes, 3)
  state.start({ ...row, allowedActions: ['requery'] }, 'requery')
  state.form.reason = '再次核查'
  const waiting = state.submit()
  await flush()
  calls[5].reject(Object.assign(new Error('原请求处理中'), { code: 601, errorCode: 'IDEMPOTENCY_IN_PROGRESS' }))
  await waiting
  assert.equal(state.uncertain.value, true)
  const check = state.submit()
  await flush()
  assert.equal(calls[6].args[2], calls[5].args[2])
  calls[6].reject(Object.assign(new Error('修订已变化'), { code: 601, errorCode: 'REVISION_CONFLICT' }))
  await check
  assert.equal(state.uncertain.value, false)
  assert.equal(hooks.leave(), true)
  state.close()
  assert.equal(state.target.value, undefined)
  state.start({ ...row, allowedActions: ['requery'] }, 'requery')
  state.form.reason = '会话隔离检查'
  const stale = state.submit()
  await flush()
  const previous = calls.at(-1)
  user.id = '2'
  assert.equal(previous.args[3].aborted, true)
  assert.equal(state.target.value, undefined)
  assert.equal(state.uncertain.value, false)
  previous.resolve({})
  await stale
  assert.equal(refreshes, 3)
  user.token = ''
  state.start({ ...row, allowedActions: ['requery'] }, 'requery')
  assert.equal(state.allowed.value, false)
  assert.equal(state.target.value, undefined)
  scope.stop()
})
