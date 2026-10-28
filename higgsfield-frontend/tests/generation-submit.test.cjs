const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

function harness(recovery) {
  if (!recovery) {
    recovery = {}
    runInNewContext(ts.transpileModule(readFileSync(require('node:path').join(__dirname,
      '../src/utils/generationRecovery.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
      { exports: recovery, structuredClone })
  }
  const auth = vue.reactive({ token: 'one', user: { permissions: [] } })
  const exports = {},
    calls = [],
    hooks = {},
    input = vue.ref({ projectId: '1', kind: 'image', modelVersionId: '2', parameters: { n: 1 } })
  let keys = 0
  const source = readFileSync(
    require('node:path').join(__dirname, '../src/composables/useGenerationSubmit.ts'),
    'utf8',
  )
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText
  const pending = (type, ...args) =>
    new Promise((resolve, reject) => calls.push({ type, args, resolve, reject }))
  runInNewContext(compiled, {
    exports,
    Error,
    AbortController,
    Date,
    crypto: { randomUUID: () => String(++keys) },
    window: { addEventListener() {}, removeEventListener() {} },
    require: (name) =>
      name.includes('utils/generationRecovery') ? recovery : name.includes('stores/auth')
        ? { useAuthStore: () => auth }
        : name === 'vue'
          ? {
              ...vue,
              onBeforeUnmount: (fn) => {
                hooks.unmount = fn
              },
              onActivated: (fn) => {
                hooks.activate = fn
              },
              onDeactivated: (fn) => {
                hooks.deactivate = fn
              },
            }
          : name === 'vue-router'
            ? {
                onBeforeRouteLeave: (fn) => {
                  hooks.leave = fn
                },
                onBeforeRouteUpdate: (fn) => {
                  hooks.update = fn
                },
              }
            : {
                validateGeneration: (...args) => pending('validate', ...args),
                submitGeneration: (...args) => pending('submit', ...args),
              },
  })
  const scope = vue.effectScope()
  const state = scope.run(() => exports.useGenerationSubmit(() => input.value))
  return {
    recovery,
    state,
    auth,
    input,
    calls,
    hooks,
    cleanup() {
      hooks.unmount()
      scope.stop()
    },
  }
}
const valid = () => ({
  valid: true,
  estimateVisibility: 'hidden',
  issues: [],
  estimateToken: 'quote',
  expiresAt: new Date(Date.now() + 60000).toISOString(),
})

test('估价仅在明确可见时展示，隐藏金额不影响合法预检提交', async () => {
  const h = harness()
  let checking = h.state.check()
  h.calls[0].resolve({ data: { ...valid(), estimate: { amount: '99.00', currency: 'CNY' } } })
  await checking
  assert.equal(h.state.visibleEstimate.value, undefined)
  const sending = h.state.submit()
  assert.equal(h.calls[1].type, 'submit')
  h.calls[1].resolve({ data: { id: '10' } })
  await sending
  checking = h.state.check()
  h.calls[2].resolve({ data: { ...valid(), estimateVisibility: 'visible', estimate: { amount: '0.00', currency: 'CNY' } } })
  await checking
  assert.equal(h.state.visibleEstimate.value.amount, '0.00')
  h.auth.user.permissions = ['changed']
  assert.equal(h.state.visibleEstimate.value, undefined)
  checking = h.state.check()
  h.calls[3].resolve({ data: { ...valid(), estimateVisibility: 'visible' } })
  await checking
  assert.equal(h.state.visibleEstimate.value, undefined)
  h.cleanup()
})

test('输入变化使旧预检失效，迟到结果不能重新开放生成', async () => {
  const h = harness()
  const check = h.state.check()
  h.input.value.parameters.n = 2
  assert.equal(h.calls[0].args[1].aborted, true)
  h.calls[0].resolve({ data: valid() })
  await check
  assert.equal(h.state.quote.value, undefined)
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  h.cleanup()
})

test('不明提交保留原请求和键，阻止离开及重复点击，成功后可打开任务', async () => {
  const h = harness()
  const check = h.state.check()
  h.calls[0].resolve({ data: valid() })
  await check
  const first = h.state.submit()
  await h.state.submit()
  assert.equal(h.calls.length, 2)
  assert.equal(h.hooks.leave(), false)
  h.calls[1].reject(Object.assign(new Error('网络中断'), { code: 0 }))
  await first
  assert.equal(h.state.uncertain.value, true)
  await h.state.check()
  assert.equal(h.calls.length, 2)
  const retry = h.state.submit()
  assert.deepEqual(h.calls[2].args, h.calls[1].args)
  h.calls[2].resolve({ data: { id: '88' } })
  await retry
  assert.equal(h.state.acceptedId.value, '88')
  assert.equal(h.state.quote.value, undefined)
  assert.equal(h.hooks.leave(), true)
  await h.state.submit()
  assert.equal(h.calls.length, 3)
  h.cleanup()
})

test('过期估价和明确业务拒绝都要求重新预检', async () => {
  const h = harness()
  let check = h.state.check()
  h.calls[0].resolve({ data: { ...valid(), expiresAt: '2000-01-01T00:00:00Z' } })
  await check
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  assert.equal(h.state.quote.value, undefined)
  check = h.state.check()
  h.calls[1].resolve({ data: valid() })
  await check
  const submit = h.state.submit()
  h.calls[2].reject(Object.assign(new Error('价格变化'), { code: 601 }))
  await submit
  assert.equal(h.state.quote.value, undefined)
  assert.equal(h.state.uncertain.value, false)
  h.cleanup()
})

test('切换账号丢弃旧预检与迟到受理结果，不允许旧账号重试', async () => {
  const h = harness()
  let checking = h.state.check()
  h.auth.token = 'two'
  h.calls[0].resolve({ data: valid() })
  await checking
  assert.equal(h.state.quote.value, undefined)
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  checking = h.state.check()
  h.calls[1].resolve({ data: valid() })
  await checking
  const sending = h.state.submit()
  h.auth.token = 'three'
  h.calls[2].resolve({ data: { id: 'old' } })
  await sending
  assert.equal(h.state.acceptedId.value, undefined)
  assert.equal(h.state.locked.value, false)
  await h.state.submit()
  assert.equal(h.calls.length, 3)
  h.cleanup()
})

test('缓存停用禁止新提交，408与处理中业务错误恢复后仍重试原目标原键', async () => {
  const h = harness()
  h.input.value.targetElementId = '9007199254740993'
  const checking = h.state.check()
  h.calls[0].resolve({ data: valid() })
  await checking
  let sending = h.state.submit()
  h.hooks.deactivate()
  h.calls[1].reject(Object.assign(new Error('超时'), { code: 408 }))
  await sending
  assert.equal(h.state.uncertain.value, true)
  assert.equal(h.hooks.update({ fullPath: '/p?tab=x' }, { fullPath: '/p?tab=y' }), false)
  await h.state.submit()
  assert.equal(h.calls.length, 2)
  h.input.value.targetElementId = '2'
  h.hooks.activate()
  sending = h.state.submit()
  assert.deepEqual(h.calls[2].args, h.calls[1].args)
  h.calls[2].reject(
    Object.assign(new Error('处理中'), { code: 601, errorCode: 'IDEMPOTENCY_IN_PROGRESS' }),
  )
  await sending
  assert.equal(h.state.uncertain.value, true)
  sending = h.state.submit()
  assert.deepEqual(h.calls[3].args, h.calls[1].args)
  h.calls[3].resolve({ data: { id: '88' } })
  await sending
  assert.equal(h.state.acceptedId.value, '88')
  h.cleanup()
})

test('权限变化和缓存停用使未提交估价失效，必须重新预检', async () => {
  const h = harness()
  let checking = h.state.check()
  h.calls[0].resolve({ data: valid() })
  await checking
  h.auth.user.permissions = ['changed']
  await h.state.submit()
  assert.equal(h.calls.length, 1)
  checking = h.state.check()
  h.hooks.deactivate()
  assert.equal(h.calls[1].args[1].aborted, true)
  h.calls[1].resolve({ data: valid() })
  await checking
  h.hooks.activate()
  await h.state.submit()
  assert.equal(h.calls.length, 2)
  assert.equal(h.state.quote.value, undefined)
  h.cleanup()
})

test('组件卸载后重新进入项目，保留原生成请求与键直到确认结果', async () => {
  const first = harness()
  const checking = first.state.check()
  first.calls[0].resolve({ data: valid() }); await checking
  const sending = first.state.submit()
  const original = first.calls[1].args
  first.cleanup()
  const reopened = harness(first.recovery)
  assert.equal(reopened.state.uncertain.value, true)
  reopened.input.value.parameters.n = 9
  await reopened.state.check()
  assert.equal(reopened.calls.length, 0)
  first.calls[1].reject(Object.assign(new Error('响应丢失'), { code: 0 })); await sending
  const retry = reopened.state.submit()
  assert.deepEqual(JSON.parse(JSON.stringify(reopened.calls[0].args)), JSON.parse(JSON.stringify(original)))
  reopened.calls[0].resolve({ data: { id: '9007199254740993' } }); await retry
  assert.equal(reopened.state.acceptedId.value, '9007199254740993')
  assert.equal(reopened.recovery.readGenerationRecovery('one', '1'), undefined)
  reopened.cleanup()
})

test('旧组件迟到成功清除同一请求，其他登录会话不能读取待确认数据', async () => {
  const first = harness()
  const checking = first.state.check()
  first.calls[0].resolve({ data: valid() }); await checking
  const sending = first.state.submit(); first.cleanup()
  first.calls[1].resolve({ data: { id: 'done' } }); await sending
  const reopened = harness(first.recovery)
  assert.equal(reopened.state.uncertain.value, false)
  reopened.recovery.saveGenerationRecovery('one', '1', { key: 'pending', data: { projectId: '1' } })
  assert.equal(reopened.recovery.readGenerationRecovery('two', '1'), undefined)
  assert.equal(reopened.recovery.readGenerationRecovery('one', '1'), undefined)
  reopened.cleanup()
})


test('点击生成自动检查并提交，重复点击不会新增请求', async () => {
  const h = harness()
  const running = h.state.generate()
  await h.state.generate()
  assert.equal(h.calls.length, 1)
  h.calls[0].resolve({ data: valid() })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(h.calls.length, 2)
  assert.equal(h.calls[1].type, 'submit')
  h.calls[1].resolve({ data: { id: '100' } })
  await running
  assert.equal(h.state.acceptedId.value, '100')
  assert.equal(h.state.generating.value, false)
  h.cleanup()
})

test('自动检查未通过不会提交任务', async () => {
  const h = harness()
  const running = h.state.generate()
  h.calls[0].resolve({ data: { valid: false, issues: [{ message: '预算不足' }] } })
  await running
  assert.equal(h.calls.length, 1)
  assert.equal(h.state.quote.value.valid, false)
  h.cleanup()
})

test('自动检查期间输入变化不会提交旧请求', async () => {
  const h = harness()
  const running = h.state.generate()
  h.input.value.parameters.n = 2
  h.calls[0].resolve({ data: valid() })
  await running
  assert.equal(h.calls.length, 1)
  assert.equal(h.state.generating.value, false)
  h.cleanup()
})
