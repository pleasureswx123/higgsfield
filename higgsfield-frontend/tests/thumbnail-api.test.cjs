const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')

test('缩略图与原图、下载使用独立授权路径并传递取消信号', async () => {
  const calls = [], api = {}
  for (const file of ['assets', 'generations']) {
    const exports = {}
    runInNewContext(ts.transpileModule(readFileSync(join(__dirname, `../src/api/${file}.ts`), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText, { exports, require: () => ({ requestBlob: options => { calls.push(options); return Promise.resolve('blob') } }) })
    Object.assign(api, exports)
  }
  const signal = new AbortController().signal, id = '9007199254740993'
  await api.readThumbnail(id, signal)
  await api.getOutputThumbnail(id, signal)
  await api.readMedia(id, false, signal, () => {})
  await api.getOutputMedia(id, true, signal)
  assert.deepEqual(calls.map(call => call.url), [
    `/api/v1/asset-versions/${id}/thumbnail`, `/api/v1/outputs/${id}/thumbnail`,
    `/api/v1/asset-versions/${id}/preview`, `/api/v1/outputs/${id}/download`,
  ])
  assert.ok(calls.every(call => call.signal === signal))
})
