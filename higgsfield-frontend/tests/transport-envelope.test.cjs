const { test } = require('node:test'),
  assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'),
  { join } = require('node:path'),
  { runInNewContext } = require('node:vm')
const { webcrypto } = require('node:crypto'),
  ts = require('typescript')
const lib = {}
runInNewContext(
  ts.transpileModule(readFileSync(join(__dirname, '../src/utils/transportEnvelope.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText,
  { exports: lib, crypto: webcrypto, btoa, atob, TextEncoder, TextDecoder, Uint8Array },
)
async function fixture() {
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
  const spki = await webcrypto.subtle.exportKey('spki', pair.publicKey)
  const metadata = {
    kid: 'test-key',
    alg: 'RSA_OAEP_AES_256_GCM',
    envelopeVersion: '1',
    expireAt: Date.now() / 1000 + 600,
    publicKey:
      '-----BEGIN PUBLIC KEY-----\n' +
      Buffer.from(spki).toString('base64') +
      '\n-----END PUBLIC KEY-----',
  }
  return { pair, metadata, context: await lib.createTransportContext(metadata) }
}
test('若依请求信封可由RSA私钥与AES-GCM解密，明文不出现在信封中', async () => {
  const { pair, context } = await fixture(),
    aad = { method: 'POST', path: '/login' },
    payload = { username: '用户', password: 'private-test-password' }
  const envelope = await lib.encryptTransportPayload(context, payload, aad)
  assert.equal(JSON.stringify(envelope).includes(payload.password), false)
  const raw = await webcrypto.subtle.decrypt(
    { name: 'RSA-OAEP' },
    pair.privateKey,
    lib.decodeTransportBytes(envelope.ek),
  )
  assert.equal(raw.byteLength, 32)
  const aes = await webcrypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['decrypt'])
  const plain = await webcrypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: lib.decodeTransportBytes(envelope.iv),
      additionalData: new TextEncoder().encode(JSON.stringify(aad)),
    },
    aes,
    lib.decodeTransportBytes(envelope.ct),
  )
  assert.deepEqual(JSON.parse(new TextDecoder().decode(plain)), payload)
  const another = await lib.encryptTransportPayload(context, payload, aad)
  assert.notEqual(envelope.iv, another.iv)
  assert.notEqual(envelope.nonce, another.nonce)
})
test('响应验证算法、密钥与请求绑定，拒绝错路径和被篡改密文', async () => {
  const { context } = await fixture(),
    request = { method: 'POST', path: '/login' },
    aad = { ...request, direction: 'response' },
    iv = webcrypto.getRandomValues(new Uint8Array(12))
  const ct = await webcrypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(JSON.stringify(aad)) },
    context.aesKey,
    new TextEncoder().encode(JSON.stringify({ code: 200, token: 'test-token' })),
  )
  const response = {
    v: '1',
    kid: context.kid,
    alg: 'AES_256_GCM',
    aad,
    iv: lib.encodeTransportBytes(iv),
    ct: lib.encodeTransportBytes(new Uint8Array(ct)),
  }
  assert.equal((await lib.decryptTransportPayload(response, context, request)).token, 'test-token')
  for (const change of [
    { kid: 'wrong' },
    { alg: 'unknown' },
    { aad: { ...aad, path: '/other' } },
    { aad: { ...aad, direction: 'request' } },
  ])
    await assert.rejects(
      () => lib.decryptTransportPayload({ ...response, ...change }, context, request),
      /不匹配/,
    )
  const damaged = lib.decodeTransportBytes(response.ct)
  damaged[0] ^= 1
  await assert.rejects(() =>
    lib.decryptTransportPayload(
      { ...response, ct: lib.encodeTransportBytes(damaged) },
      context,
      request,
    ),
  )
})
test('公钥过期与未知协议在加密前拒绝', async () => {
  const { metadata } = await fixture()
  await assert.rejects(() => lib.createTransportContext({ ...metadata, expireAt: 0 }), /有效期/)
  await assert.rejects(
    () => lib.createTransportContext({ ...metadata, envelopeVersion: '2' }),
    /协议/,
  )
})
