const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { webcrypto } = require('node:crypto')
const ts = require('typescript')
function load(file, dependencies = {}, globals = {}) {
  const exports = {}
  runInNewContext(
    ts.transpileModule(readFileSync(join(__dirname, '../src', file), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    {
      exports,
      require: (name) => {
        assert.ok(name in dependencies, name)
        return dependencies[name]
      },
      crypto: webcrypto,
      btoa,
      atob,
      TextEncoder,
      TextDecoder,
      Uint8Array,
      ArrayBuffer,
      Blob,
      FormData,
      URLSearchParams,
      URL,
      DOMException,
      ...globals,
    },
  )
  return exports
}
const crypto = load('utils/transportEnvelope.ts')
const transport = load('api/transport.ts', { '@/utils/transportEnvelope': crypto })
const fixture = (async () => {
  const pair = await webcrypto.subtle.generateKey(
    {
      name: 'RSA-OAEP',
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: 'SHA-256',
    },
    true,
    ['encrypt', 'decrypt'],
  )
  const key = {
    kid: 'test',
    alg: 'RSA_OAEP_AES_256_GCM',
    envelopeVersion: '1',
    expireAt: Date.now() / 1000 + 600,
    publicKey:
      '-----BEGIN PUBLIC KEY-----\n' +
      Buffer.from(await webcrypto.subtle.exportKey('spki', pair.publicKey)).toString('base64') +
      '\n-----END PUBLIC KEY-----',
  }
  async function decrypt(envelope) {
    const raw = await webcrypto.subtle.decrypt(
      { name: 'RSA-OAEP' },
      pair.privateKey,
      crypto.decodeTransportBytes(envelope.ek),
    )
    const aes = await webcrypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, [
      'encrypt',
      'decrypt',
    ])
    const plain = await webcrypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: crypto.decodeTransportBytes(envelope.iv),
        additionalData: new TextEncoder().encode(JSON.stringify(envelope.aad)),
      },
      aes,
      crypto.decodeTransportBytes(envelope.ct),
    )
    return { payload: JSON.parse(new TextDecoder().decode(plain)), aes }
  }
  async function respond(envelope, payload) {
    const { aes } = await decrypt(envelope),
      aad = { ...envelope.aad, direction: 'response' },
      iv = webcrypto.getRandomValues(new Uint8Array(12))
    const ct = await webcrypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(JSON.stringify(aad)) },
      aes,
      new TextEncoder().encode(JSON.stringify(payload)),
    )
    return {
      v: '1',
      kid: 'test',
      alg: 'AES_256_GCM',
      aad,
      iv: crypto.encodeTransportBytes(iv),
      ct: crypto.encodeTransportBytes(new Uint8Array(ct)),
    }
  }
  return {
    key,
    decrypt,
    respond,
    privateKey:
      '-----BEGIN PRIVATE KEY-----\n' +
      Buffer.from(await webcrypto.subtle.exportKey('pkcs8', pair.privateKey)).toString('base64') +
      '\n-----END PRIVATE KEY-----',
  }
})()
const active = { transportCryptoActive: true }
test('登录表单与查询正文可解密；DELETE使用同一密钥且防重放随机数独立', async () => {
  const { key, decrypt } = await fixture
  const form = await transport.prepareTransportRequest(
    {
      url: '/login',
      method: 'POST',
      data: new URLSearchParams({ username: '用户', password: 'secret' }),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    },
    active,
    async () => key,
  )
  assert.equal(form.config.data.includes('secret'), false)
  const envelope = Object.fromEntries(new URLSearchParams(form.config.data))
  envelope.aad = JSON.parse(envelope.aad)
  assert.deepEqual((await decrypt(envelope)).payload, { username: '用户', password: 'secret' })
  const result = await transport.prepareTransportRequest(
    { url: '/items?kind=image', method: 'DELETE', params: { ids: [1, 2] }, data: { revision: 3 } },
    active,
    async () => key,
  )
  const query = JSON.parse(
    new TextDecoder().decode(crypto.decodeTransportBytes(result.config.params.__enc)),
  )
  assert.equal(result.config.url, '/items')
  assert.equal(query.ek, result.config.data.ek)
  assert.notEqual(query.nonce, result.config.data.nonce)
  assert.deepEqual((await decrypt(query)).payload, { kind: 'image', ids: [1, 2] })
  assert.deepEqual((await decrypt(result.config.data)).payload, { revision: 3 })
})
test('长度限制、取消、非法路径均阻止发送；排除接口和二进制不改写', async () => {
  const { key } = await fixture
  for (const url of [
    'https://evil.test/login',
    '//evil.test/login',
    '/x/../login',
    '/\\evil.test/login',
  ])
    assert.throws(() => transport.transportPath(url))
  await assert.rejects(
    () =>
      transport.prepareTransportRequest(
        { url: '/items' },
        { ...active, maxEncryptedGetUrlLength: 20 },
        async () => key,
      ),
    /长度/,
  )
  await assert.rejects(
    () =>
      transport.prepareTransportRequest(
        { url: '/items', signal: { aborted: true } },
        active,
        async () => {
          throw Error('不应读密钥')
        },
      ),
    { name: 'AbortError' },
  )
  await assert.rejects(
    () => transport.prepareTransportRequest({ url: '/items?a=1&a=2' }, active, async () => key),
    /重复/,
  )
  for (const config of [{ url: '/plain' }]) {
    assert.equal(
      (
        await transport.prepareTransportRequest(
          config,
          { ...active, excludePaths: ['/plain'] },
          async () => {
            throw Error('不应读密钥')
          },
        )
      ).config,
      config,
    )
  }
})
function clientFor(adapter, fetcher) {
  return load(
    'api/client.ts',
    {
      './transport': transport,
      '@/utils/transportEnvelope': crypto,
      axios: { default: { create: () => adapter, isAxiosError: () => false } },
    },
    { fetch: fetcher },
  )
}
test('客户端解密登录成功和HTTP业务错误，并复用元数据而不重放写入', async () => {
  const { key, respond } = await fixture,
    calls = []
  let requests = 0
  const client = clientFor({
    get: async (url) => {
      calls.push(url)
      return {
        data: {
          code: 200,
          data: url.endsWith('frontend-config')
            ? { ...active, configExpireAt: Date.now() / 1000 + 600 }
            : key,
        },
      }
    },
    request: async (config) => {
      requests++
      assert.equal(config.headers['X-Transport-Encrypt'], '1')
      const envelope = Object.fromEntries(new URLSearchParams(config.data))
      envelope.aad = JSON.parse(envelope.aad)
      return {
        status: requests === 1 ? 200 : 409,
        headers: { 'x-body-encrypted': '1', 'x-key-id': 'test' },
        data: await respond(
          envelope,
          requests === 1
            ? { code: 200, token: 'ok' }
            : { code: 409, msg: '冲突', data: { errorCode: 'REVISION_CONFLICT' } },
        ),
      }
    },
  })
  const config = {
    url: '/login',
    method: 'POST',
    data: new URLSearchParams({ password: 'secret' }),
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  }
  assert.equal((await client.request(config, false)).token, 'ok')
  await assert.rejects(
    () => client.request(config, false),
    (e) => e.code === 409 && e.errorCode === 'REVISION_CONFLICT',
  )
  assert.equal(requests, 2)
  assert.equal(calls.length, 2)
})
test('策略失败不发送登录，身份在准备期间变化不发送旧令牌', async () => {
  let sent = 0
  const failed = clientFor({
    get: async () => {
      throw Error('策略失败')
    },
    request: async () => {
      sent++
    },
  })
  await assert.rejects(
    () => failed.request({ url: '/login', method: 'POST', data: { password: 'secret' } }, false),
    /策略失败/,
  )
  assert.equal(sent, 0)
  let token = 'old'
  const changed = clientFor({
    get: async () => {
      token = 'new'
      return { data: { code: 200, data: { transportCryptoActive: false } } }
    },
    request: async () => {
      sent++
    },
  })
  changed.configureAuth(
    () => token,
    () => {},
  )
  await assert.rejects(() => changed.request({ url: '/getInfo' }), { name: 'AbortError' })
  assert.equal(sent, 0)
})

// 显式启用本机后端环境验证，不要求普通前端测试安装Python依赖。
test(
  '前端信封由真实Python工具解密，后端响应由前端解密',
  { skip: process.env.HF_RUN_CRYPTO_INTEROP !== '1' },
  async () => {
    const { spawnSync } = require('node:child_process')
    const { key, privateKey } = await fixture
    const request = await transport.prepareTransportRequest(
      { url: '/login', method: 'POST', data: { username: '跨语言用户', password: 'interop-only' } },
      active,
      async () => key,
    )
    const backend = join(__dirname, '../../ruoyi-fastapi-backend')
    const script = `import json, sys
from unittest.mock import patch
from utils.transport_crypto_util import TransportCryptoUtil, TransportKeyProvider
value=json.load(sys.stdin)
with patch.object(TransportKeyProvider, 'get_private_key_pem', return_value=value['privateKey']):
    decoded=TransportCryptoUtil.decrypt_envelope(value['envelope'], 'POST', '/login')
    payload=json.loads(decoded.plaintext)
    assert payload == {'username':'跨语言用户','password':'interop-only'}
    response=TransportCryptoUtil.encrypt_response_body(decoded.aes_key, json.dumps({'code':200,'token':'python-response'}).encode(), decoded.kid, 'POST','/login')
    print(response.decode())
`
    const result = spawnSync(join(backend, '.venv/Scripts/python.exe'), ['-c', script], {
      cwd: backend,
      encoding: 'utf8',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      input: JSON.stringify({ privateKey, envelope: request.config.data }),
      timeout: 30000,
    })
    assert.equal(result.status, 0, result.stderr)
    const response = JSON.parse(result.stdout.trim())
    assert.equal(
      (await crypto.decryptTransportPayload(response, request.context, request.aad)).token,
      'python-response',
    )
  },
)

test('启用范围遵循后端中间件，requiredPaths不会越过enabledPaths', async () => {
  const config = { url: '/outside', method: 'POST', data: { name: '保留' } }
  const result = await transport.prepareTransportRequest(
    config,
    { ...active, enabledPaths: ['/enabled'], requiredPaths: ['/outside'] },
    async () => {
      throw Error('不应读密钥')
    },
  )
  assert.equal(result.config, config)
})

test(
  '真实ASGI中间件还原表单及查询正文，拒绝重放与防重放存储不可用',
  { skip: process.env.HF_RUN_CRYPTO_INTEROP !== '1' },
  async () => {
    const { spawnSync } = require('node:child_process')
    const { key, privateKey } = await fixture
    const login = await transport.prepareTransportRequest(
      {
        url: '/login',
        method: 'POST',
        data: new URLSearchParams({ username: '中间件用户', password: 'test-only' }),
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      },
      active,
      async () => key,
    )
    const deletion = await transport.prepareTransportRequest(
      { url: '/items', method: 'DELETE', params: { ids: ['11', '12'] }, data: { revision: 7 } },
      active,
      async () => key,
    )
    const unavailable = await transport.prepareTransportRequest(
      {
        url: '/login',
        method: 'POST',
        data: new URLSearchParams({ username: '禁止调用', password: 'test-only' }),
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      },
      active,
      async () => key,
    )
    const wire = (prepared) => ({
      ...prepared.config,
      data:
        typeof prepared.config.data === 'string'
          ? prepared.config.data
          : JSON.stringify(prepared.config.data),
    })
    const backend = join(__dirname, '../../ruoyi-fastapi-backend')
    // 使用模块入口，确保后端自身模块可从工程根目录导入。
    const result = spawnSync(
      join(backend, '.venv/Scripts/python.exe'),
      ['-m', 'tests.transport_middleware_bridge'],
      {
        cwd: backend,
        encoding: 'utf8',
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        timeout: 30000,
        input: JSON.stringify({
          privateKey,
          requests: [
            { config: wire(login) },
            { config: wire(login) },
            { config: wire(deletion) },
            { config: wire(unavailable), disableReplayStore: true },
          ],
        }),
      },
    )
    assert.equal(result.status, 0, result.stderr)
    const output = JSON.parse(result.stdout.trim())
    assert.deepEqual(output.visits, ['login', 'items'])
    const prepared = [login, login, deletion, unavailable]
    const decoded = []
    for (let i = 0; i < 4; i++) {
      assert.equal(output.responses[i].headers['x-body-encrypted'], '1')
      decoded.push(
        await crypto.decryptTransportPayload(
          output.responses[i].data,
          prepared[i].context,
          prepared[i].aad,
        ),
      )
    }
    assert.deepEqual(JSON.parse(JSON.stringify(decoded[0].data)), {
      username: '中间件用户',
      password: 'test-only',
    })
    assert.match(decoded[1].msg, /重放/)
    assert.equal(output.responses[2].status, 409)
    assert.equal(decoded[2].data.errorCode, 'REVISION_CONFLICT')
    assert.deepEqual(JSON.parse(JSON.stringify(decoded[2].data.ids)), ['11', '12'])
    assert.equal(decoded[2].data.body.revision, 7)
    assert.match(decoded[3].msg, /防重放校验不可用/)
  },
)

test('登录API通过统一加密客户端发送完整表单，并保留用户名规范化', async () => {
  const { key, decrypt, respond } = await fixture
  let received
  const client = clientFor({
    get: async (url) => ({
      data: { code: 200, data: url.endsWith('frontend-config') ? active : key },
    }),
    request: async (config) => {
      assert.equal(config.url, '/login')
      assert.equal(config.headers.Authorization, undefined)
      const envelope = Object.fromEntries(new URLSearchParams(config.data))
      envelope.aad = JSON.parse(envelope.aad)
      received = (await decrypt(envelope)).payload
      return {
        status: 200,
        headers: { 'x-body-encrypted': '1' },
        data: await respond(envelope, { code: 200, token: 'login-test-token' }),
      }
    },
  })
  client.configureAuth(
    () => 'old-token',
    () => {},
  )
  const auth = load('api/auth.ts', { './client': client })
  const result = await auth.login({
    username: '  用户  ',
    password: 'test-only',
    code: '1234',
    uuid: 'captcha-id',
  })
  assert.equal(result.token, 'login-test-token')
  assert.deepEqual(received, {
    username: '用户',
    password: 'test-only',
    code: '1234',
    uuid: 'captcha-id',
  })
})

test('密钥轮换失败只清理旧缓存，显式重试刷新公钥，迟到失败不清理新密钥', async () => {
  const { key } = await fixture
  let keyReads = 0,
    writes = 0,
    releaseLate,
    releaseFirst
  const seen = []
  const client = clientFor({
    get: async (url) => ({
      data: {
        code: 200,
        data: url.endsWith('frontend-config')
          ? { ...active, configExpireAt: Date.now() / 1000 + 600 }
          : { ...key, kid: ++keyReads === 1 ? 'old-key' : 'new-key' },
      },
    }),
    request: async (config) => {
      writes++
      seen.push(config.data.kid)
      const failure = {
        status: 200,
        headers: { 'x-transport-crypto-status': 'kid_mismatch' },
        data: { code: 500, msg: '密钥版本不存在' },
      }
      if (writes === 1)
        return new Promise((resolve) => {
          releaseFirst = () => resolve(failure)
        })
      if (writes === 2)
        return new Promise((resolve) => {
          releaseLate = () => resolve(failure)
        })
      return { status: 200, headers: {}, data: { code: 200 } }
    },
  })
  const config = {
    url: '/items',
    method: 'POST',
    data: { name: '轮换' },
    headers: { 'Idempotency-Key': 'same-intent' },
  }
  // 两次准备共享同一旧公钥；第二次响应故意延迟到新公钥已经缓存之后。
  const first = client.request(config)
  const firstResult = assert.rejects(() => first, /密钥版本不存在/)
  while (!releaseFirst) await new Promise((resolve) => setImmediate(resolve))
  const late = client.request(config)
  const lateResult = assert.rejects(() => late, /密钥版本不存在/)
  while (!releaseLate) await new Promise((resolve) => setImmediate(resolve))
  releaseFirst()
  await firstResult
  assert.equal(writes, 2)
  await client.request(config)
  assert.equal(keyReads, 2)
  releaseLate()
  await lateResult
  await client.request(config)
  assert.equal(keyReads, 2)
  assert.deepEqual(seen, ['old-key', 'old-key', 'new-key', 'new-key'])
})

test('后端切换强制加密后，下一次显式请求刷新策略而非自动重放', async () => {
  const { key } = await fixture
  let policies = 0,
    writes = 0
  const client = clientFor({
    get: async (url) => ({
      data: {
        code: 200,
        data: url.endsWith('frontend-config')
          ? { transportCryptoActive: ++policies > 1, configExpireAt: Date.now() / 1000 + 600 }
          : key,
      },
    }),
    request: async (config) => {
      writes++
      if (writes === 1) {
        assert.equal(config.headers['X-Transport-Encrypt'], undefined)
        return {
          status: 200,
          headers: { 'x-transport-crypto-status': 'required_missing' },
          data: { code: 500, msg: '当前接口要求使用加密传输' },
        }
      }
      assert.equal(config.headers['X-Transport-Encrypt'], '1')
      return { status: 200, headers: {}, data: { code: 200 } }
    },
  })
  await assert.rejects(
    () => client.request({ url: '/items', method: 'POST', data: { name: '策略变化' } }),
    /要求使用加密/,
  )
  assert.equal(writes, 1)
  await client.request({ url: '/items', method: 'POST', data: { name: '策略变化' } })
  assert.equal(writes, 2)
  assert.equal(policies, 2)
})

test('分片上传保留二进制和范围头，查询加密并返回可解密上下文', async () => {
  const { key, decrypt } = await fixture,
    body = new Uint8Array([0, 255, 1, 128])
  const result = await transport.prepareTransportRequest(
    {
      url: '/upload',
      method: 'PUT',
      data: body,
      params: { part: '2' },
      headers: { 'Content-Type': 'application/octet-stream', 'Content-Range': 'bytes 0-3/4' },
    },
    active,
    async () => key,
  )
  assert.equal(result.config.data, body)
  assert.equal(result.config.headers['Content-Range'], 'bytes 0-3/4')
  assert.equal(result.config.headers['X-Transport-Encrypt'], '1')
  const envelope = JSON.parse(
    new TextDecoder().decode(crypto.decodeTransportBytes(result.config.params.__enc)),
  )
  assert.deepEqual((await decrypt(envelope)).payload, { part: '2' })
  await assert.rejects(
    () =>
      transport.prepareTransportRequest(
        {
          url: '/upload',
          method: 'PUT',
          data: body,
          headers: { 'Content-Type': 'application/json' },
        },
        active,
        async () => key,
      ),
    /二进制上传/,
  )
})

test(
  'required模式中间件接收加密查询和原始分片字节，并加密上传回执',
  { skip: process.env.HF_RUN_CRYPTO_INTEROP !== '1' },
  async () => {
    const { spawnSync } = require('node:child_process'),
      { key, privateKey } = await fixture
    const body = new Uint8Array([0, 255, 13, 10, 128, 42])
    const request = await transport.prepareTransportRequest(
      {
        url: '/upload',
        method: 'PUT',
        data: body,
        params: { part: '2' },
        headers: { 'Content-Type': 'application/octet-stream', 'Content-Range': 'bytes 0-5/6' },
      },
      active,
      async () => key,
    )
    const backend = join(__dirname, '../../ruoyi-fastapi-backend')
    const result = spawnSync(
      join(backend, '.venv/Scripts/python.exe'),
      ['-m', 'tests.transport_middleware_bridge'],
      {
        cwd: backend,
        encoding: 'utf8',
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        timeout: 30000,
        input: JSON.stringify({
          privateKey,
          requests: [
            {
              config: { ...request.config, data: undefined },
              bodyBase64: Buffer.from(body).toString('base64'),
            },
          ],
        }),
      },
    )
    assert.equal(result.status, 0, result.stderr)
    const output = JSON.parse(result.stdout.trim()),
      response = output.responses[0]
    assert.deepEqual(output.visits, ['upload'])
    assert.equal(response.headers['x-body-encrypted'], '1')
    const decoded = await crypto.decryptTransportPayload(
      response.data,
      request.context,
      request.aad,
    )
    assert.deepEqual(JSON.parse(JSON.stringify(decoded.data)), {
      bytes: [0, 255, 13, 10, 128, 42],
      part: '2',
      range: 'bytes 0-5/6',
    })
  },
)

test('下载使用加密查询并保留Range，文件字节原样返回，加密错误不作为文件', async () => {
  const { key, respond } = await fixture,
    blob = new Blob([new Uint8Array([0, 255, 7])], { type: 'application/octet-stream' })
  let count = 0,
    expired = 0
  const client = clientFor({
    get: async (url) => ({
      data: { code: 200, data: url.endsWith('frontend-config') ? active : key },
    }),
    request: async (config) => {
      count++
      assert.equal(config.responseType, 'blob')
      assert.equal(config.headers.Range, 'bytes=0-2')
      const envelope = JSON.parse(
        new TextDecoder().decode(crypto.decodeTransportBytes(config.params.__enc)),
      )
      if (count === 1) return { status: 206, headers: {}, data: blob }
      return {
        status: 200,
        headers: { 'x-body-encrypted': '1', 'x-key-id': key.kid },
        data: new Blob(
          [
            JSON.stringify(
              await respond(envelope, {
                code: 401,
                msg: '访问已撤回',
                data: { errorCode: 'ACCESS_REVOKED' },
              }),
            ),
          ],
          { type: 'application/json' },
        ),
      }
    },
  })
  client.configureAuth(
    () => 'token',
    () => expired++,
  )
  const config = { url: '/download', headers: { Range: 'bytes=0-2' } }
  assert.equal(await client.requestBlob(config), blob)
  await assert.rejects(
    () => client.requestBlob(config),
    (e) => e.code === 401 && e.errorCode === 'ACCESS_REVOKED' && e.message === '访问已撤回',
  )
  assert.equal(expired, 1)
})

test('下载准备期间身份变化不发送旧令牌，策略失败不发送下载', async () => {
  let token = 'old',
    sent = 0
  const client = clientFor({
    get: async () => {
      token = 'new'
      return { data: { code: 200, data: { transportCryptoActive: false } } }
    },
    request: async () => sent++,
  })
  client.configureAuth(
    () => token,
    () => {},
  )
  await assert.rejects(() => client.requestBlob({ url: '/download' }), { name: 'AbortError' })
  const failed = clientFor({
    get: async () => {
      throw Error('策略不可用')
    },
    request: async () => sent++,
  })
  await assert.rejects(() => failed.requestBlob({ url: '/download' }), /策略不可用/)
  assert.equal(sent, 0)
})

test('SSE加密连接查询并保留游标与原始事件流，加密撤权错误不进入事件解析', async () => {
  const { key, decrypt, respond } = await fixture
  let connections = 0,
    expired = 0
  const signal = new AbortController().signal
  const client = clientFor(
    {
      get: async (url) => ({
        data: { code: 200, data: url.endsWith('frontend-config') ? active : key },
      }),
    },
    async (url, config) => {
      connections++
      assert.equal(config.headers['Last-Event-ID'], 'event-42')
      assert.equal(config.signal, signal)
      assert.equal(config.headers.Authorization, 'Bearer test-token')
      assert.equal(config.headers['X-Transport-Encrypt'], '1')
      const envelope = JSON.parse(
        new TextDecoder().decode(
          crypto.decodeTransportBytes(new URL(url, 'https://test').searchParams.get('__enc')),
        ),
      )
      assert.deepEqual((await decrypt(envelope)).payload, { limit: '10' })
      if (connections === 1)
        return new Response('id: event-43\ndata: {"state":"running"}\n\n', {
          headers: { 'Content-Type': 'text/event-stream' },
        })
      return new Response(
        JSON.stringify(
          await respond(envelope, {
            code: 401,
            msg: '事件访问撤回',
            data: { errorCode: 'ACCESS_REVOKED' },
          }),
        ),
        {
          headers: {
            'Content-Type': 'application/json',
            'x-body-encrypted': '1',
            'x-key-id': key.kid,
          },
        },
      )
    },
  )
  client.configureAuth(
    () => 'test-token',
    () => expired++,
  )
  const stream = await client.requestEventStream('/events?limit=10', 'event-42', signal)
  assert.equal(await new Response(stream).text(), 'id: event-43\ndata: {"state":"running"}\n\n')
  await assert.rejects(
    () => client.requestEventStream('/events?limit=10', 'event-42', signal),
    (e) => e.code === 401 && e.errorCode === 'ACCESS_REVOKED',
  )
  assert.equal(expired, 1)
  assert.equal(connections, 2)
})

test('SSE关闭策略保留原查询，身份变化不建立连接', async () => {
  let token = 'old',
    sent = 0
  const client = clientFor(
    { get: async () => ({ data: { code: 200, data: { transportCryptoActive: false } } }) },
    async (url) => {
      sent++
      assert.equal(url, '/dev-api/events?after=42')
      return new Response('data: ok\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
    },
  )
  client.configureAuth(
    () => token,
    () => {},
  )
  await client.requestEventStream('/events?after=42', undefined, new AbortController().signal)
  const changed = clientFor(
    {
      get: async () => {
        token = 'new'
        return { data: { code: 200, data: { transportCryptoActive: false } } }
      },
    },
    async () => {
      sent++
    },
  )
  changed.configureAuth(
    () => token,
    () => {},
  )
  await assert.rejects(
    () => changed.requestEventStream('/events', undefined, new AbortController().signal),
    { name: 'AbortError' },
  )
  assert.equal(sent, 1)
})

test(
  '真实required中间件透传下载字节和SSE事件，客户端解密两类拒绝响应',
  { skip: process.env.HF_RUN_CRYPTO_INTEROP !== '1' },
  async () => {
    const { spawnSync } = require('node:child_process'),
      { key, privateKey } = await fixture
    const backend = join(__dirname, '../../ruoyi-fastapi-backend')
    function send(config) {
      const result = spawnSync(
        join(backend, '.venv/Scripts/python.exe'),
        ['-m', 'tests.transport_middleware_bridge'],
        {
          cwd: backend,
          encoding: 'utf8',
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
          timeout: 15000,
          input: JSON.stringify({ privateKey, requests: [{ config }] }),
        },
      )
      assert.equal(result.status, 0, result.stderr)
      return JSON.parse(result.stdout.trim()).responses[0]
    }
    const client = clientFor(
      {
        get: async (url) => ({
          data: { code: 200, data: url.endsWith('frontend-config') ? active : key },
        }),
        request: async (config) => {
          const response = send({ ...config, method: 'GET' })
          return {
            ...response,
            data: new Blob([Buffer.from(response.bodyBase64, 'base64')], {
              type: response.headers['content-type'],
            }),
          }
        },
      },
      async (url, config) => {
        const parsed = new URL(url, 'https://test')
        const response = send({
          url: parsed.pathname.replace('/dev-api', ''),
          method: 'GET',
          params: Object.fromEntries(parsed.searchParams),
          headers: config.headers,
        })
        return new Response(Buffer.from(response.bodyBase64, 'base64'), {
          status: response.status,
          headers: response.headers,
        })
      },
    )
    let expired = 0
    client.configureAuth(
      () => 'fixture',
      () => expired++,
    )
    const file = await client.requestBlob({ url: '/download', headers: { Range: 'bytes=0-2' } })
    assert.deepEqual([...new Uint8Array(await file.arrayBuffer())], [0, 255, 7])
    await assert.rejects(
      () => client.requestBlob({ url: '/download?denied=1', headers: { Range: 'bytes=0-2' } }),
      (e) => e.code === 401 && e.message === '下载权限失效',
    )
    const stream = await client.requestEventStream(
      '/events?limit=10',
      '42',
      new AbortController().signal,
    )
    assert.equal(
      await new Response(stream).text(),
      'id: 43\ndata: {"state":"running"}\n\nid: 44\ndata: {"state":"succeeded"}\n\n',
    )
    await assert.rejects(
      () =>
        client.requestEventStream('/events?limit=10&denied=1', '42', new AbortController().signal),
      (e) => e.code === 401 && e.message === '事件权限失效',
    )
    assert.equal(expired, 2)
  },
)
