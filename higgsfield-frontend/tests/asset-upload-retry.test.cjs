const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { webcrypto } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(code) { super('expired'); this.code = code } }
for (const terminal of ['failed', 'cancelled', 'expired', '410', 'network']) {
  test(`重试会话 ${terminal}`, async () => {
    const exports = {}, creates = [], binds = []
    let reads = 0
    const api = {
      createUpload: async (...args) => { creates.push(args); return { data: { id: String(creates.length) } } },
      readUpload: async id => {
        reads++
        if (reads === 1) throw new Error('模拟断网')
        if (id === '1' && terminal === '410') throw new ApiError(410)
        return { data: { id, state: id === '1' && terminal !== 'network' ? terminal : 'ready' } }
      },
      bindAsset: async (...args) => binds.push(args),
    }
    runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useAssetUploads.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
      exports, crypto: webcrypto, AbortController, Error,
      require(name) {
        if (name === 'vue') return { ...vue, onActivated() {}, onDeactivated() {}, onBeforeUnmount() {} }
        if (name.includes('stores/auth')) return { useAuthStore: () => ({ token: 'test' }) }
        if (name.includes('api/client')) return { ApiError }
        if (name.includes('api/assets')) return api
        if (name.includes('assetFormats')) return { assetUploadMime: () => 'image/jpeg' }
        return { hashBlob: async () => 'sha' }
      },
    })
    const scope = vue.effectScope()
    const state = scope.run(() => exports.useAssetUploads('1', () => {}))
    const settle = async () => { for (let i=0; i<30 && state.running.value; i++) await new Promise(setImmediate) }
    state.enqueue([{ name:'download.jpg', size:10, type:'image/jpeg' }], '2')
    await settle()
    assert.equal(state.items[0].stage, 'failed')
    state.retry(state.items[0]); await settle()
    assert.equal(state.items[0].stage, 'done')
    assert.equal(creates.length, terminal === 'network' ? 1 : 2)
    if (creates.length === 2) assert.notEqual(creates[0][3], creates[1][3])
    assert.equal(binds.length, 1)
    assert.equal(binds[0][3], '2')
    scope.stop()
  })
}
