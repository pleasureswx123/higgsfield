import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch } from 'vue'
import { webcrypto } from 'node:crypto'
import { pricePublishPayload } from '../../src/utils/pricePublish.js'
const form = () => ({
  effectiveFrom: '2026-11-01 00:00:00',
  effectiveUntil: '',
  reason: ' 审核通过 ',
  replaceActivationId: '',
  expectedActivationRevision: '',
})
test('发布时间明确上海时区，替换必须携带成对版本，禁止逆序区间', () => {
  const result = pricePublishPayload(form(), '9')
  assert.equal(Date.parse(result.effectiveFrom), Date.parse('2026-10-31T16:00:00Z'))
  assert.equal(result.effectiveUntil, null)
  assert.equal(result.reason, '审核通过')
  assert.throws(() => pricePublishPayload({ ...form(), replaceActivationId: '3' }, '9'), /同时/)
  assert.throws(
    () => pricePublishPayload({ ...form(), effectiveUntil: '2026-10-31 00:00:00' }, '9'),
    /晚于/
  )
  const replaced = pricePublishPayload(
    { ...form(), replaceActivationId: '9007199254740993', expectedActivationRevision: '2' },
    '9'
  )
  assert.equal(replaced.replaceActivationId, '9007199254740993')
})
test('发布使用快照修订，失败保留幂等键，权限控制提交', async () => {
  const calls = [],
    hooks = {},
    user = reactive({ token: 'session-one', id: '1', permissions: ['billing:price:publish'] })
  const context = createContext({ crypto: webcrypto, AbortController })
  let leaveConfirmation
  const mocks = {
    'element-plus': { ElMessageBox: { confirm: () => new Promise((resolve, reject) => { leaveConfirmation = { resolve, reject } }) } },
    vue: {
      watch,
      onActivated: fn => { hooks.activate = fn },
      onDeactivated: fn => { hooks.deactivate = fn },
      computed,
      reactive,
      ref,
      onBeforeUnmount: (fn) => {
        hooks.unmount = fn
      },
    },
    'vue-router': {
      onBeforeRouteLeave: (fn) => {
        hooks.leave = fn
      },
    },
    '@/store/modules/user': { default: () => user },
    '@/utils/pricePublish': { pricePublishPayload },
    '@/api/studio/prices': {
      publishPrice: (...args) =>
        new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/usePricePublish.js', import.meta.url),
      'utf8'
    ),
    { context }
  )
  await module.link(
    (name) =>
      new SyntheticModule(
        Object.keys(mocks[name]),
        function () {
          for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
        },
        { context }
      )
  )
  await module.evaluate()
  const state = module.namespace.usePricePublish(() => {})
  state.start({ id: '1', revision: '2', validationIssues: [{}] })
  assert.equal(state.open.value, false)
  const target = { id: '1', revision: '2', validationIssues: [] }
  state.start(target)
  target.revision = '3'
  Object.assign(state.form, form())
  state.formRef.value = { validate: async () => true }
  const flush = () => new Promise((resolve) => setImmediate(resolve))
  const first = state.submit()
  await flush()
  assert.equal(calls[0].args[1].revision, '2')
  assert.equal(hooks.leave(), false)
  calls[0].reject(new Error('连接中断'))
  await first
  assert.equal(state.uncertain.value, true)
  assert.equal(hooks.leave(), false)
  state.close()
  assert.equal(state.open.value, true)
  state.form.reason = '不能改变原请求'
  state.start({ ...target, id: 'different' })
  assert.equal(state.version.value.id, '1')
  const retry = state.submit()
  await flush()
  assert.equal(calls[0].args[2], calls[1].args[2])
  assert.equal(calls[1].args[1].reason, calls[0].args[1].reason)
  calls[1].resolve({ data: {} })
  await retry
  assert.equal(state.uncertain.value, false)
  state.start(target)
  Object.assign(state.form, form())
  const conflict = state.submit()
  await flush()
  calls[2].reject(Object.assign(new Error('版本冲突'), { code: 601, errorCode: 'REVISION_CONFLICT' }))
  await conflict
  assert.equal(state.uncertain.value, false)
  const cancelLeave = hooks.leave()
  leaveConfirmation.reject(new Error('继续编辑'))
  assert.equal(await cancelLeave, false)
  assert.equal(state.form.reason, form().reason)
  const allowLeave = hooks.leave()
  leaveConfirmation.resolve()
  assert.equal(await allowLeave, true)
  state.close()
  assert.equal(state.open.value, false)
  state.start(target)
  user.permissions = []
  await state.submit()
  assert.equal(calls.length, 3)
  assert.equal(state.open.value, false)
  assert.equal(state.version.value, undefined)
  user.permissions = ['billing:price:publish']
  state.start(target)
  Object.assign(state.form, form())
  const hidden = state.submit()
  await flush()
  hooks.deactivate()
  assert.equal(calls[3].args[3].aborted, true)
  assert.equal(state.uncertain.value, true)
  await state.submit()
  assert.equal(calls.length, 4)
  calls[3].resolve({ data: {} })
  await hidden
  assert.equal(state.open.value, true)
  hooks.activate()
  const confirm = state.submit()
  await flush()
  assert.equal(calls[4].args[2], calls[3].args[2])
  user.id = '2'
  assert.equal(calls[4].args[3].aborted, true)
  assert.equal(state.open.value, false)
  assert.equal(state.uncertain.value, false)
  state.start(target)
  state.form.reason = '新用户输入'
  calls[4].resolve({ data: {} })
  await confirm
  assert.equal(state.open.value, true)
  assert.equal(state.form.reason, '新用户输入')
  const staleLeave = hooks.leave()
  user.token = ''
  leaveConfirmation.resolve()
  assert.equal(await staleLeave, false)
  assert.equal(state.open.value, false)
  await state.submit()
  assert.equal(calls.length, 5)
  hooks.unmount()
})
