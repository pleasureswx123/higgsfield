const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
function load(path, context = {}) {
  const exports = {}
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src', path), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports, ...context })
  return exports
}
const formats = load('utils/assetFormats.ts')
test('文档扩展名兼容空MIME，未知文件不进入素材上传队列', () => {
  assert.equal(formats.assetUploadMime({ name: '脚本.MD', type: '' }), 'text/markdown')
  assert.equal(formats.assetUploadMime({ name: '演示.pptx', type: 'application/zip' }), formats.documentFormats.pptx)
  assert.equal(formats.assetUploadMime({ name: '应用.exe', type: 'application/octet-stream' }), '')
  assert.equal(formats.assetExtension(formats.documentFormats.docx), '.docx')
})
test('文档预览保留源码，切换与关闭拒绝迟到正文，下载走原件接口', async () => {
  const calls = [], revoked = [], anchors = [], hooks = {}, auth = vue.reactive({ token: 'token' })
  const pending = (kind, ...args) => new Promise(resolve => calls.push({ kind, args, resolve }))
  const library = load('composables/useAssetLibrary.ts', {
    AbortController, URL: { createObjectURL: () => 'blob:document', revokeObjectURL: value => revoked.push(value) },
    document: { createElement: () => { const a = { click() {} }; anchors.push(a); return a } },
    require(name) {
      if (name === 'vue') return { ...vue, onActivated() {}, onDeactivated(fn) { hooks.deactivate = fn }, onBeforeUnmount(fn) { hooks.unmount = fn } }
      if (name.includes('assetFormats')) return formats
      if (name.includes('libraryWindow')) return { libraryWindow: () => ({}) }
      if (name.includes('stores/auth')) return { useAuthStore: () => auth }
      return { listAssets: async () => ({ rows: [], total: 0 }), readDocumentText: (...args) => pending('text', ...args), readMedia: (...args) => pending('media', ...args) }
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => library.useAssetLibrary('9007199254740993', vue.ref(null)))
  const asset = { id: '1', name: '页面', mediaType: 'document', currentVersionId: '9', file: { mimeType: 'text/html' } }
  const old = state.openMedia(asset), current = state.openMedia({ ...asset, currentVersionId: '10' })
  assert.equal(calls[0].args[1].aborted, true)
  calls[1].resolve({ data: { sections: ['<script>alert(1)</script>'] } }); await current
  calls[0].resolve({ data: { sections: ['旧正文'] } }); await old
  assert.equal(state.documentSections.value[0], '<script>alert(1)</script>')
  assert.equal(state.mediaUrl.value, '')
  const download = state.openMedia(asset, true)
  assert.equal(state.documentSections.value.length, 0)
  assert.equal(calls[2].kind, 'media'); assert.equal(calls[2].args[1], true)
  calls[2].resolve(new Blob(['original'])); await download
  assert.equal(anchors[0].download, '页面.html')
  hooks.deactivate()
  assert.equal(state.selected.value, null); assert.deepEqual(revoked, ['blob:document'])
  hooks.unmount(); scope.stop()
})
