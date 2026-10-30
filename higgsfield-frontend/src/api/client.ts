import axios, { type AxiosRequestConfig } from 'axios'
import { prepareTransportRequest, transportPath, type TransportPolicy } from './transport'
import { decryptTransportPayload, type TransportPublicKey } from '@/utils/transportEnvelope'
export class ApiError extends Error {
  constructor(
    message: string,
    public code: number,
    public errorCode?: string,
  ) {
    super(message)
  }
}
interface Envelope {
  code: number
  msg?: string
  success?: boolean
  data?: unknown
}
// 凭据由制作端 Store 注入，标签页会话独立恢复，不读取管理端 Cookie。
let readToken: () => string = () => ''
let onExpired: () => void = () => {}
export function configureAuth(token: () => string, expired: () => void) {
  readToken = token
  onExpired = expired
}
const client = axios.create({ baseURL: '/dev-api', timeout: 15000 })
/** 策略只在内存短暂缓存；读取失败不降级，也不自动重放业务写请求。 */
let policyCache: { value: TransportPolicy; until: number } | undefined
let policyPending: Promise<TransportPolicy> | undefined
async function readTransportPolicy(): Promise<TransportPolicy> {
  if (policyCache && policyCache.until > Date.now()) return policyCache.value
  if (policyPending) return policyPending
  policyPending = (async () => {
    const { data } = await client.get('/transport/crypto/frontend-config')
    if (data?.code !== 200 || typeof data.data?.transportCryptoActive !== 'boolean')
      throw new Error('无法确认服务器传输策略，请稍后重试')
    const value = data.data as TransportPolicy & { configExpireAt?: number }
    const expires = Number(value.configExpireAt) * 1000
    policyCache = {
      value,
      until: Number.isFinite(expires) ? Math.min(expires, Date.now() + 60000) : Date.now(),
    }
    return value
  })()
  try {
    return await policyPending
  } finally {
    policyPending = undefined
  }
}
let keyCache: TransportPublicKey | undefined
let keyPending: Promise<TransportPublicKey> | undefined
async function readTransportKey(): Promise<TransportPublicKey> {
  if (keyCache && keyCache.expireAt * 1000 > Date.now() + 5000) return keyCache
  if (keyPending) return keyPending
  keyPending = (async () => {
    const { data } = await client.get('/transport/crypto/public-key')
    if (data?.code !== 200 || !data.data) throw new Error('无法读取服务器传输公钥')
    keyCache = data.data as TransportPublicKey
    return keyCache
  })()
  try {
    return await keyPending
  } finally {
    keyPending = undefined
  }
}
/** 失败只影响当前使用的缓存，不自动重放业务操作。 */
function invalidateTransportCache(status: unknown, policy: TransportPolicy, kid?: string) {
  if (status === 'kid_mismatch' && kid && kid === keyCache?.kid) keyCache = undefined
  if (
    ['required_missing', 'protocol_version_invalid', 'algorithm_invalid'].includes(
      String(status),
    ) &&
    policyCache?.value === policy
  )
    policyCache = undefined
}
// 浏览器Axios不提供逐块响应；SSE在同一鉴权边界使用fetch流，令牌只放请求头。
export async function requestEventStream(
  path: string,
  cursor: string | undefined,
  signal: AbortSignal,
) {
  const token = readToken()
  const policy = await readTransportPolicy()
  const prepared = await prepareTransportRequest(
    { url: path, method: 'GET', signal },
    policy,
    readTransportKey,
  )
  if (token !== readToken()) throw new DOMException('登录状态已变化', 'AbortError')
  const query = prepared.config.params ? new URLSearchParams(prepared.config.params).toString() : ''
  const url = `${prepared.config.url}${query ? '?' + query : ''}`
  const response = await fetch(`/dev-api${url}`, {
    signal,
    credentials: 'omit',
    cache: 'no-store',
    headers: {
      ...(prepared.config.headers as Record<string, string>),
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
      ...(cursor ? { 'Last-Event-ID': cursor } : {}),
      'X-Timezone': 'Asia/Shanghai',
    },
  })
  invalidateTransportCache(
    response.headers.get('x-transport-crypto-status'),
    policy,
    prepared.context?.kid,
  )
  const encrypted = response.headers.get('x-body-encrypted') === '1'
  if (
    encrypted ||
    !response.ok ||
    !response.headers.get('content-type')?.includes('text/event-stream')
  ) {
    let body = await response.json().catch(() => null)
    if (encrypted) {
      if (!prepared.context || !prepared.aad) throw new Error('响应缺少对应的传输加密上下文')
      const keyId = response.headers.get('x-key-id')
      if (keyId && keyId !== prepared.context.kid) throw new Error('响应传输密钥不匹配')
      body = await decryptTransportPayload(body, prepared.context, prepared.aad)
    }
    const code = body?.code ?? response.status
    if (code === 401 && token === readToken()) onExpired()
    throw new ApiError(body?.msg || '任务事件连接失败', code, body?.data?.errorCode)
  }
  if (!response.body) throw new ApiError('浏览器不支持流式响应', 0)
  return response.body
}
// 媒体同样经过授权；框架可能用 HTTP 200 返回 JSON 业务错误。
export async function requestBlob(config: AxiosRequestConfig): Promise<Blob> {
  const token = readToken()
  const policy = await readTransportPolicy()
  const prepared = await prepareTransportRequest(
    { ...config, responseType: 'blob' },
    policy,
    readTransportKey,
  )
  if (token !== readToken()) throw new DOMException('登录状态已变化', 'AbortError')
  const response = await client.request<Blob>({
    ...prepared.config,
    responseType: 'blob',
    validateStatus: () => true,
    headers: {
      ...prepared.config.headers,
      Authorization: `Bearer ${token}`,
      'X-Timezone': 'Asia/Shanghai',
    },
  })
  invalidateTransportCache(
    response.headers['x-transport-crypto-status'],
    policy,
    prepared.context?.kid,
  )
  const encrypted = String(response.headers['x-body-encrypted']) === '1'
  let json =
    encrypted || response.data.type.includes('json')
      ? await response.data.text().then((value) => JSON.parse(value))
      : null
  if (encrypted) {
    if (!prepared.context || !prepared.aad) throw new Error('响应缺少对应的传输加密上下文')
    const keyId = response.headers['x-key-id']
    if (keyId && keyId !== prepared.context.kid) throw new Error('响应传输密钥不匹配')
    json = await decryptTransportPayload(json, prepared.context, prepared.aad)
  }
  const code = json?.code ?? response.status
  if (code === 401 && token === readToken()) onExpired()
  if (json || response.status >= 400) {
    throw new ApiError(json?.msg || json?.detail || '媒体读取失败', code, json?.data?.errorCode)
  }
  return response.data
}
export async function request<T extends Envelope>(
  config: AxiosRequestConfig,
  authenticated = true,
): Promise<T> {
  const token = authenticated ? readToken() : ''
  try {
    const path = transportPath(config.url)
    const metadata =
      path === '/transport/crypto/frontend-config' || path === '/transport/crypto/public-key'
    const policy = metadata ? { transportCryptoActive: false } : await readTransportPolicy()
    const prepared = await prepareTransportRequest(config, policy, readTransportKey)
    // 策略/密钥读取期间身份已变化时，不发送旧会话请求。
    if (authenticated && token !== readToken())
      throw new DOMException('登录状态已变化', 'AbortError')
    const response = await client.request({
      ...prepared.config,
      validateStatus: () => true,
      headers: {
        ...prepared.config.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'X-Timezone': 'Asia/Shanghai',
      },
    })
    invalidateTransportCache(
      response.headers['x-transport-crypto-status'],
      policy,
      prepared.context?.kid,
    )
    let data = response.data as T
    if (String(response.headers['x-body-encrypted']) === '1') {
      if (!prepared.context || !prepared.aad) throw new Error('响应缺少对应的传输加密上下文')
      const keyId = response.headers['x-key-id']
      if (keyId && keyId !== prepared.context.kid) throw new Error('响应传输密钥不匹配')
      data = (await decryptTransportPayload(data, prepared.context, prepared.aad)) as T
    }
    if (response.status >= 400) {
      if (response.status === 401 && token === readToken() && authenticated) onExpired()
      throw new ApiError(
        data?.msg || (response.status === 429 ? '请求过于频繁，请稍后重试' : '请求失败，请重试'),
        response.status,
        (data?.data as { errorCode?: string } | undefined)?.errorCode,
      )
    }
    if (data.code !== 200 || data.success === false) {
      if (data.code === 401 && token === readToken() && authenticated) onExpired()
      const details = data.data as { errorCode?: string } | undefined
      throw new ApiError(data.msg || '请求失败，请重试', data.code, details?.errorCode)
    }
    return data
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (axios.isAxiosError(error)) {
      const status = error.response?.status || 0
      if (status === 401 && token === readToken() && authenticated) onExpired()
      throw new ApiError(
        error.response?.data?.msg ||
          (status === 429
            ? '请求过于频繁，请稍后重试'
            : status === 401
              ? '登录已过期，请重新登录'
              : '暂时无法连接服务，请检查后端并重试'),
        status,
      )
    }
    throw error
  }
}
