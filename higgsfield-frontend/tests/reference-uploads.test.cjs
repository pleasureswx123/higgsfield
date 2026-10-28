const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function setup() {
  const exports = {}, hooks = {}, calls = [], writes = []
  const auth = vue.reactive({ token: 'one', user: { user: { userId: 1 }, permissions: [] } })
  const folder = vue.ref('2'), disabled = vue.ref(false)
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useReferenceUploads.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, Error, require(name) {
      if (name === 'vue') return { ...vue, onBeforeUnmount: fn => hooks.close = fn }
      if (name.includes('stores/auth')) return { useAuthStore: () => auth }
      if (name.includes('projectWorkspace')) return { readBrief: () => new Promise(resolve => calls.push(resolve)) }
      if (name.includes('assetFormats')) return { assetUploadMime: file => file.type }
      return { useAssetUploads: () => ({ enqueue: (...args) => writes.push(args), pause() {} }) }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports.useReferenceUploads('1', () => folder.value, () => disabled.value, () => {}))
  return { state, calls, writes, folder, disabled, auth, close() { hooks.close(); scope.stop() } }
}
const image = { name: 'reference.png', type: 'image/png' }
const allowed = { data: { allowedActions: ['asset:upload', 'asset:create', 'asset:reference'] } }
test('上传参考素材固定选择时目录，核验完整权限后才入队', async () => {
  const h = setup(), pending = h.state.enqueue([image])
  h.folder.value = '3'; h.calls[0](allowed); await pending
  assert.equal(h.writes.length, 1); assert.equal(h.writes[0][1], '2'); h.close()
})
test('缺少引用授权与文档文件均不上传', async () => {
  const h = setup(), pending = h.state.enqueue([image])
  h.calls[0]({ data: { allowedActions: ['asset:upload', 'asset:create'] } }); await pending
  assert.equal(h.writes.length, 0); assert.match(h.state.error.value, /权限/)
  await h.state.enqueue([{ type: 'application/pdf' }]); assert.equal(h.calls.length, 1)
  assert.match(h.state.error.value, /图片或视频/); h.close()
})
test('关闭弹窗或切换账号时迟到授权不能触发上传', async () => {
  for (const change of [h => h.disabled.value = true, h => h.auth.token = 'two']) {
    const h = setup(), pending = h.state.enqueue([image]); change(h)
    h.calls[0](allowed); await pending
    assert.equal(h.writes.length, 0); assert.equal(h.state.checking.value, false); h.close()
  }
})
