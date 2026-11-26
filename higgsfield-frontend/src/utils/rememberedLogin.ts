/** 仅在用户主动勾选后保存。账号与密码一同加密，密钥保存在本浏览器的 IndexedDB 中。 */
const recordKey = 'higgsfield.studio.remembered-login'
export const rememberPeriod = 7 * 24 * 60 * 60 * 1000

interface Credentials {
  username: string
  password: string
}

async function deviceKey(create: boolean): Promise<CryptoKey> {
  // 内网 HTTP 的兼容实现不能结构化克隆 CryptoKey，改为持久化本机随机生成的密钥材料。
  const candidate = !create ? undefined : window.isSecureContext
    ? await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
    : crypto.getRandomValues(new Uint8Array(32))
  const stored = await new Promise<CryptoKey | Uint8Array<ArrayBuffer>>((resolve, reject) => {
    const open = indexedDB.open('higgsfield.studio.login-keys', 1)
    open.onupgradeneeded = () => open.result.createObjectStore('keys')
    open.onerror = () => reject(open.error)
    open.onsuccess = () => {
      const db = open.result
      const tx = db.transaction('keys', create ? 'readwrite' : 'readonly')
      const keys = tx.objectStore('keys')
      const read = keys.get('device')
      let key: typeof candidate
      read.onsuccess = () => {
        key = read.result ?? candidate
        if (!read.result && candidate) keys.put(candidate, 'device')
      }
      tx.oncomplete = () => {
        db.close()
        if (key) resolve(key)
        else reject(new Error('已保存的登录信息不可用'))
      }
      tx.onabort = () => { db.close(); reject(tx.error) }
    }
  })
  return stored instanceof Uint8Array
    ? crypto.subtle.importKey('raw', stored, 'AES-GCM', false, ['encrypt', 'decrypt'])
    : stored
}

export function forgetLogin() {
  localStorage.removeItem(recordKey)
}

async function seal(value: object) {
  const key = await deviceKey(true)
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const clear = new TextEncoder().encode(JSON.stringify(value))
  const cipher = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, clear)
  return { iv: Array.from(iv), ciphertext: Array.from(new Uint8Array(cipher)) }
}

interface Envelope {
  iv: number[]
  ciphertext: number[]
}

async function unseal(record: Envelope) {
  const key = await deviceKey(false)
  const clear = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: Uint8Array.from(record.iv) },
    key, Uint8Array.from(record.ciphertext))
  return JSON.parse(new TextDecoder().decode(clear))
}

export async function rememberLogin(credentials: Credentials, expires: number) {
  const envelope = await seal(credentials)
  localStorage.setItem(recordKey, JSON.stringify({ ...envelope, version: 2, expires }))
}

export async function readRememberedLogin(): Promise<(Credentials & { expires: number }) | undefined> {
  const raw = localStorage.getItem(recordKey)
  if (!raw) return
  try {
    const record = JSON.parse(raw)
    // 旧版本的截止时间按首次保存时刻折算为七天。
    const expires = record.version === 2 ? record.expires : record.expires - 23 * 86400000
    if (Number.isFinite(expires) && expires > Date.now()) {
      const data = await unseal(record)
      if (typeof data.username === 'string' && typeof data.password === 'string') return { ...data, expires }
    }
  } catch {
    // 清除过期或无法解密的记录，保留正常登录入口。
  }
  if (localStorage.getItem(recordKey) === raw) forgetLogin()
}

export const deviceSessionKey = 'higgsfield.studio.device-session'

export async function writeDeviceSession(token: string, expires: number) {
  const id = crypto.randomUUID()
  const envelope = await seal({ token, expires })
  localStorage.setItem(deviceSessionKey, JSON.stringify({ ...envelope, id }))
  return id
}

export async function readDeviceSession(): Promise<{ id: string; token: string; expires: number } | undefined> {
  const raw = localStorage.getItem(deviceSessionKey)
  if (!raw) return
  try {
    const record = JSON.parse(raw)
    const data = await unseal(record)
    if (typeof data.token === 'string' && data.token && Number.isFinite(data.expires) && data.expires > Date.now()
      && typeof record.id === 'string' && localStorage.getItem(deviceSessionKey) === raw) {
      return { id: record.id, token: data.token, expires: data.expires }
    }
  } catch { /* 无法读取的设备会话交由用户重新登录。 */ }
  if (localStorage.getItem(deviceSessionKey) === raw) localStorage.removeItem(deviceSessionKey)
}

export function removeDeviceSession(id: string) {
  const raw = localStorage.getItem(deviceSessionKey)
  if (raw && JSON.parse(raw).id === id) localStorage.removeItem(deviceSessionKey)
}
