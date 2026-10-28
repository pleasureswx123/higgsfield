import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch } from 'vue'
import { webcrypto } from 'node:crypto'
import { priceEndPayload } from '../../src/utils/pricePublish.js'
const form = () => ({ effectiveUntil: '2026-11-02 00:00:00', reason: '缩短区间' })
test('结束区间使用快照修订，失败保留幂等键，权限控制提交', async () => {
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
    '@/utils/pricePublish': { priceEndPayload },
    '@/api/studio/prices': {
      endPriceActivation: (...args) =>
        new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/usePriceActivationEnd.js', import.meta.url),
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
  const state = module.namespace.usePriceActivationEnd(() => {})
  state.start({})
  assert.equal(state.open.value, false)
  const target = {
    id: '1',
    revision: '2',
    effectiveFrom: '2026-11-01T00:00:00+08:00',
    effectiveUntil: null,
  }
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

test('区间结束只允许缩短，保留起点，开放区间可设置终点', () => {
  const row = {
    id: '1',
    revision: '2',
    effectiveFrom: '2026-11-01T00:00:00+08:00',
    effectiveUntil: null,
  }
  assert.equal(priceEndPayload(form(), row).revision, '2')
  assert.throws(
    () => priceEndPayload({ ...form(), effectiveUntil: '2026-11-01 00:00:00' }, row),
    /缩短/
  )
  assert.throws(
    () => priceEndPayload(form(), { ...row, effectiveUntil: '2026-11-02T00:00:00+08:00' }),
    /缩短/
  )
  assert.throws(
    () => priceEndPayload(form(), { ...row, effectiveUntil: '2026-11-01T12:00:00+08:00' }),
    /缩短/
  )
  assert.equal(
    Date.parse(priceEndPayload(form(), row).effectiveUntil),
    Date.parse('2026-11-01T16:00:00Z')
  )
})
