import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'

// 执行真实请求拦截器，仅替换浏览器持久化、网络和提示组件。
async function harness() {
  const handlers = {},
    persisted = [],
    logs = []
  const service = {
    interceptors: Object.fromEntries(
      ['request', 'response'].map((name) => [
        name,
        {
          use: (success, failure) => {
            handlers[name] = { success, failure }
          },
        },
      ])
    ),
  }
  const noop = () => {}
  const mocks = {
    axios: { default: { defaults: { headers: {} }, create: () => service, isCancel: () => false } },
    'element-plus': { ElNotification: {}, ElMessageBox: {}, ElMessage: noop, ElLoading: {} },
    '@/utils/auth': { getToken: () => 'test-token' },
    '@/utils/time': { getDisplayTimezone: () => 'Asia/Shanghai' },
    '@/utils/errorCode': { default: {} },
    '@/utils/ruoyi': { tansParams: noop, blobValidate: noop },
    '@/plugins/cache': {
      default: { session: { getJSON: () => null, setJSON: (...args) => persisted.push(args) } },
    },
    'file-saver': { saveAs: noop },
    '@/store/modules/user': { default: noop },
    '@/utils/transportCrypto': {
      decryptTransportErrorResponse: async (v) => v,
      decryptTransportResponse: async (v) => v,
      encryptTransportRequest: async (v) => v,
      invalidateTransportKeyMeta: noop,
      resetTransportRequestConfig: noop,
      shouldRetryTransportWithFreshKey: () => false,
    },
  }
  const context = createContext({
    console: { log: (...args) => logs.push(args), warn: (...args) => logs.push(args) },
  })
  const module = new SourceTextModule(
    await readFile(new URL('../../src/utils/request.js', import.meta.url), 'utf8'),
    {
      context,
      initializeImportMeta: (meta) => {
        meta.env = { VITE_APP_BASE_API: '/dev-api' }
      },
    }
  )
  await module.link((specifier) => {
    const namespace = mocks[specifier]
    assert.ok(namespace, specifier)
    return new SyntheticModule(
      Object.keys(namespace),
      function () {
        for (const [key, value] of Object.entries(namespace)) this.setExport(key, value)
      },
      { context }
    )
  })
  await module.evaluate()
  return { handlers, persisted, logs, context }
}

test('异常与费用写API通过真实拦截器保留错误码、幂等键和中止信号', async () => {
  for (const [file, name] of [['incidents', 'recoverIncident'], ['prices', 'publishPrice'], ['prices', 'endPriceActivation'], ['billing', 'adjustBillingEvent']]) {
  const controller = new AbortController()
  const { handlers, context } = await harness()
  let mode = 'REVISION_CONFLICT'
  const api = new SourceTextModule(
    await readFile(new URL(`../../src/api/studio/${file}.js`, import.meta.url), 'utf8'), { context },
  )
  await api.link(() => new SyntheticModule(['default'], function () {
    this.setExport('default', config => {
      assert.equal(config.headers['Idempotency-Key'], 'original-key')
      assert.equal(config.businessErrorDetails, true)
      assert.equal(config.signal, controller.signal)
      assert.equal(config.headers.repeatSubmit, false)
      if (mode === 'http') return handlers.response.failure({
        config, message: 'HTTP拒绝', response: { status: 409, data: { msg: '冲突' } },
      })
      return handlers.response.success({ config, request: { responseType: '' }, data: { code: 601, msg: '业务拒绝', data: { errorCode: mode } } })
    })
  }, { context }))
  await api.evaluate()
  for (const code of ['REVISION_CONFLICT', 'IDEMPOTENCY_IN_PROGRESS']) {
    mode = code
    await assert.rejects(api.namespace[name]('1', { revision: '2' }, 'original-key', controller.signal), cause => {
      assert.equal(cause.code, 601)
      assert.equal(cause.errorCode, code)
      return true
    })
  }
  mode = 'http'
  await assert.rejects(api.namespace[name]('1', { revision: '2' }, 'original-key', controller.signal), cause => {
    assert.equal(cause.response.status, 409)
    return true
  })
  }
})

test('凭据POST不进入会话缓存，普通请求保留防重机制', async () => {
  const { handlers, persisted } = await harness()
  const data = { apiKey: 'test-only-secret' }
  await handlers.request.success({
    method: 'post',
    url: '/credentials',
    data,
    headers: {},
    sensitiveRequest: true,
  })
  assert.equal(persisted.length, 0)
  await handlers.request.success({
    method: 'post',
    url: '/normal',
    data: { name: '正常请求' },
    headers: {},
  })
  assert.equal(persisted.length, 1)
})

test('凭据失败不输出原异常或向页面传递请求配置', async () => {
  const { handlers, logs } = await harness()
  const secret = 'test-only-secret'
  const error = {
    message: secret,
    config: { sensitiveRequest: true, data: { apiKey: secret } },
    response: { data: { msg: secret } },
  }
  for (const callback of [handlers.request.failure, handlers.response.failure]) {
    await assert.rejects(callback(error), (safe) => {
      assert.equal(safe.config, undefined)
      assert.equal(safe.response, undefined)
      assert.ok(!safe.message.includes(secret))
      return true
    })
  }
  await assert.rejects(
    handlers.response.success({
      config: { sensitiveRequest: true },
      data: { code: 601, msg: secret },
    }),
    (safe) => !safe.message.includes(secret)
  )
  assert.equal(logs.length, 0)
})
