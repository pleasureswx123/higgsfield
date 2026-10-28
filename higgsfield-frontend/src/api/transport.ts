import type { AxiosRequestConfig } from 'axios'
import {
  createTransportContext,
  encryptTransportPayload,
  encodeTransportBytes,
  type TransportPublicKey,
} from '@/utils/transportEnvelope'
export interface TransportPolicy {
  transportCryptoActive: boolean
  envelopeVersion?: string
  requestEnvelopeAlgorithm?: string
  responseEnvelopeAlgorithm?: string
  enabledPaths?: string[]
  requiredPaths?: string[]
  excludePaths?: string[]
  maxEncryptedGetUrlLength?: number
}
function checkAborted(config: AxiosRequestConfig) {
  if (config.signal?.aborted) throw new DOMException('请求已取消', 'AbortError')
}
const matches = (path: string, prefixes: string[] = []) =>
  prefixes.some((prefix) => path === prefix || path.startsWith(prefix + '/'))
/** 路径必须来自平台相对接口，避免将凭据或密钥发送到外部地址。 */
export function transportPath(url = '') {
  if (
    !url.startsWith('/') ||
    url.startsWith('//') ||
    url.includes('#') ||
    url.includes('\\') ||
    new URL(url, 'https://platform.invalid').pathname !== url.split('?')[0]
  )
    throw new Error('传输加密仅支持平台相对接口地址')
  return url.split('?')[0]!
}
export async function prepareTransportRequest(
  config: AxiosRequestConfig,
  policy: TransportPolicy,
  readKey: () => Promise<TransportPublicKey>,
) {
  const path = transportPath(config.url)
  if (typeof policy.transportCryptoActive !== 'boolean') throw new Error('服务器传输策略格式无效')
  if (
    !policy.transportCryptoActive ||
    matches(path, ['/transport/crypto/frontend-config', '/transport/crypto/public-key']) ||
    matches(path, policy.excludePaths) ||
    (policy.enabledPaths?.length && !matches(path, policy.enabledPaths))
  )
    return { config }
  if (
    (policy.envelopeVersion && String(policy.envelopeVersion) !== '1') ||
    (policy.requestEnvelopeAlgorithm &&
      policy.requestEnvelopeAlgorithm !== 'RSA_OAEP_AES_256_GCM') ||
    (policy.responseEnvelopeAlgorithm && policy.responseEnvelopeAlgorithm !== 'AES_256_GCM')
  )
    throw new Error('服务器传输加密协议不受支持')
  const method = (config.method || 'GET').toUpperCase()
  if (!['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'].includes(method))
    throw new Error('此请求方法不支持传输加密')
  const headers = { ...config.headers } as Record<string, unknown>
  const contentType = String(
    Object.entries(headers).find(([key]) => key.toLowerCase() === 'content-type')?.[1] || '',
  )
  // 文件正文保持原始字节；使用加密查询建立会话，JSON回执仍由同一会话解密。
  const rawBody =
    config.data instanceof Blob ||
    config.data instanceof ArrayBuffer ||
    ArrayBuffer.isView(config.data) ||
    config.data instanceof FormData ||
    contentType.includes('multipart/form-data') ||
    contentType.includes('application/octet-stream')
  if (
    rawBody &&
    (contentType.includes('application/json') ||
      contentType.includes('application/x-www-form-urlencoded'))
  )
    throw new Error('二进制上传不能声明为JSON或表单编码')
  if (rawBody && !contentType && !(config.data instanceof FormData))
    headers['Content-Type'] = 'application/octet-stream'
  checkAborted(config)
  const context = await createTransportContext(await readKey())
  checkAborted(config)
  const aad = { method, path }
  const query = new URLSearchParams(config.url?.split('?')[1] || '')
  const inline = Object.fromEntries(query)
  if (new Set(query.keys()).size !== [...query.keys()].length)
    throw new Error('加密查询不支持重复URL参数，请使用params数组')
  if (
    config.params instanceof URLSearchParams &&
    new Set(config.params.keys()).size !== [...config.params.keys()].length
  )
    throw new Error('加密查询不支持重复URL参数，请使用params数组')
  const params =
    config.params instanceof URLSearchParams ? Object.fromEntries(config.params) : config.params
  const next = { ...config, url: path, headers }
  if (
    rawBody ||
    method === 'GET' ||
    method === 'HEAD' ||
    method === 'DELETE' ||
    config.params ||
    query.size
  ) {
    const envelope = await encryptTransportPayload(context, { ...inline, ...params }, aad)
    next.params = {
      __enc: encodeTransportBytes(new TextEncoder().encode(JSON.stringify(envelope))),
    }
    const limit = policy.maxEncryptedGetUrlLength ?? 4096
    if (
      !Number.isFinite(limit) ||
      limit <= 0 ||
      path.length + 1 + new URLSearchParams(next.params).toString().length > limit
    )
      throw new Error('加密查询参数长度超限，请缩小查询范围')
  }
  if (!rawBody && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const payload =
      config.data instanceof URLSearchParams ? Object.fromEntries(config.data) : config.data
    const envelope = await encryptTransportPayload(context, payload, aad)
    if (contentType.includes('application/x-www-form-urlencoded')) {
      next.data = new URLSearchParams(
        Object.entries(envelope).map(([key, value]) => [
          key,
          typeof value === 'object' ? JSON.stringify(value) : String(value),
        ]),
      ).toString()
    } else {
      next.data = envelope
      for (const key of Object.keys(headers))
        if (key.toLowerCase() === 'content-type') delete headers[key]
      headers['Content-Type'] = 'application/json;charset=utf-8'
    }
  }
  headers['X-Transport-Encrypt'] = '1'
  headers['X-Key-Id'] = context.kid
  checkAborted(config)
  return { config: next as AxiosRequestConfig, context, aad }
}
