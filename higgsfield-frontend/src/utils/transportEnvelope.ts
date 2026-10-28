/** 与若依现有传输协议一致；每个请求独立密钥，不持久化明文或密钥。 */
export interface TransportPublicKey {
  kid: string
  alg: string
  envelopeVersion: string
  publicKey: string
  expireAt: number
}
export interface TransportContext {
  kid: string
  aesKey: CryptoKey
  ek: string
}
export interface TransportAad {
  method: string
  path: string
}
export function encodeTransportBytes(bytes: Uint8Array): string {
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}
export function decodeTransportBytes(value: string): Uint8Array<ArrayBuffer> {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('传输加密编码无效')
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(
    atob(normalized + '='.repeat((4 - (normalized.length % 4)) % 4)),
    (character) => character.charCodeAt(0),
  )
}
function browserCrypto() {
  if (!globalThis.crypto?.subtle) throw new Error('当前浏览器环境不支持安全传输加密，请使用 HTTPS')
  return globalThis.crypto
}
export async function createTransportContext(
  metadata: TransportPublicKey,
): Promise<TransportContext> {
  if (
    !metadata.kid ||
    metadata.alg !== 'RSA_OAEP_AES_256_GCM' ||
    String(metadata.envelopeVersion) !== '1' ||
    !Number.isFinite(metadata.expireAt) ||
    metadata.expireAt <= Date.now() / 1000
  )
    throw new Error('服务器传输公钥协议或有效期无效')
  const crypto = browserCrypto()
  const pem = metadata.publicKey.replace(
    /-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s+/g,
    '',
  )
  const der = Uint8Array.from(atob(pem), (character) => character.charCodeAt(0))
  const publicKey = await crypto.subtle.importKey(
    'spki',
    der,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  )
  const aesKey = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, [
    'encrypt',
    'decrypt',
  ])
  const rawKey = await crypto.subtle.exportKey('raw', aesKey)
  const encryptedKey = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, rawKey)
  return { kid: metadata.kid, aesKey, ek: encodeTransportBytes(new Uint8Array(encryptedKey)) }
}
export async function encryptTransportPayload(
  context: TransportContext,
  payload: unknown,
  aad: TransportAad,
) {
  const crypto = browserCrypto()
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const bytes = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(JSON.stringify(aad)) },
    context.aesKey,
    new TextEncoder().encode(JSON.stringify(payload ?? {})),
  )
  return {
    v: '1',
    kid: context.kid,
    alg: 'RSA_OAEP_AES_256_GCM',
    ts: Math.floor(Date.now() / 1000),
    nonce: crypto.randomUUID(),
    ek: context.ek,
    aad,
    iv: encodeTransportBytes(iv),
    ct: encodeTransportBytes(new Uint8Array(bytes)),
  }
}
export async function decryptTransportPayload(
  value: unknown,
  context: TransportContext,
  request: TransportAad,
): Promise<unknown> {
  if (!value || typeof value !== 'object') throw new Error('传输响应信封格式无效')
  const envelope = value as {
    v?: string
    alg?: string
    kid?: string
    iv?: string
    ct?: string
    aad?: TransportAad & { direction?: string }
  }
  if (
    String(envelope.v) !== '1' ||
    envelope.alg !== 'AES_256_GCM' ||
    envelope.kid !== context.kid ||
    !envelope.iv ||
    !envelope.ct ||
    envelope.aad?.method !== request.method ||
    envelope.aad.path !== request.path ||
    envelope.aad.direction !== 'response'
  )
    throw new Error('传输响应信封与当前请求不匹配')
  const iv = decodeTransportBytes(envelope.iv)
  if (iv.byteLength !== 12) throw new Error('传输响应随机向量长度无效')
  const plain = await browserCrypto().subtle.decrypt(
    { name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(JSON.stringify(envelope.aad)) },
    context.aesKey,
    decodeTransportBytes(envelope.ct),
  )
  return JSON.parse(new TextDecoder().decode(plain))
}
