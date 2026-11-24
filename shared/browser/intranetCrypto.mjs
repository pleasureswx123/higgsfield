/** 内网 HTTP 保留原有请求加密协议；随机数始终来自浏览器系统随机源。 */
export async function prepareBrowserCrypto(loadFallback, loadForge) {
  if (typeof crypto.randomUUID !== 'function') {
    Object.defineProperty(crypto, 'randomUUID', { value() {
      const bytes = crypto.getRandomValues(new Uint8Array(16))
      bytes[6] = (bytes[6] & 15) | 64
      bytes[8] = (bytes[8] & 63) | 128
      const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
      return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-')
    } })
  }
  if (!crypto.subtle) {
    const [fallback, {default: forge}] = await Promise.all([loadFallback(), loadForge()])
    const subtle = fallback.crypto.subtle
    const publicKeys = new WeakMap()
    function bytes(value) {
      return ArrayBuffer.isView(value) ? new Uint8Array(value.buffer, value.byteOffset, value.byteLength) : new Uint8Array(value)
    }
    function binary(value) {
      return Array.from(bytes(value), byte => String.fromCharCode(byte)).join('')
    }
    // 内网 HTTP 的 RSA 公钥封装与服务端 OpenSSL 使用相同的 OAEP 和 MGF1 摘要。
    const methods = {
      async importKey(format, raw, algorithm, extractable, usages) {
        const key = await subtle.importKey(format, raw, algorithm, extractable, usages)
        if (format === 'spki' && key.algorithm.name === 'RSA-OAEP' && key.algorithm.hash.name === 'SHA-256') {
          publicKeys.set(key, forge.pki.publicKeyFromAsn1(forge.asn1.fromDer(binary(raw))))
        }
        return key
      },
      async encrypt(algorithm, key, data) {
        if (algorithm.name === 'RSA-OAEP' && publicKeys.has(key) && key.usages.includes('encrypt')) {
          const ciphertext = publicKeys.get(key).encrypt(binary(data), 'RSA-OAEP', {
            md: forge.md.sha256.create(), mgf1: {md: forge.md.sha256.create()},
            label: algorithm.label ? binary(algorithm.label) : '',
            seed: binary(crypto.getRandomValues(new Uint8Array(32))),
          })
          return Uint8Array.from(ciphertext, character => character.charCodeAt(0)).buffer
        }
        return subtle.encrypt(algorithm, key, data)
      },
    }
    Object.defineProperty(crypto, 'subtle', { value: new Proxy(subtle, {
      get(target, property) {
        if (Object.hasOwn(methods, property)) return methods[property]
        const value = Reflect.get(target, property, target)
        return typeof value === 'function' ? value.bind(target) : value
      },
    }) })
  }
}
