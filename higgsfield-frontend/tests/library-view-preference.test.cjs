const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
test('素材偏好保持项目字符串范围，支持的恢复才触发页面修改', async () => {
  const exports = {}, calls = [], applied = []
  let controls
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useLibraryViewPreference.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, Error, require(id) {
      if (id === './useProjectViewPreference') return { useViewPreference: (current, apply, read, write) => { controls = { current, apply, read, write }; return controls } }
      return { getLibraryViewPreference: async (...args) => { calls.push(args) }, saveLibraryViewPreference: async (...args) => { calls.push(args) } }
    },
  })
  const value = { layout: 'masonry', fileType: 'image', cardSize: 5, splitByDate: true }
  exports.useLibraryViewPreference('9007199254740993', () => value, item => applied.push(item))
  controls.apply(value); assert.equal(applied[0], value)
  controls.apply({ ...value, fileType: 'pdf' })
  assert.equal(applied[1].fileType, 'pdf')
  await controls.read(); await controls.write(value, '3', 'same-request-key')
  assert.equal(calls[0][0], '9007199254740993'); assert.equal(calls[1][0], calls[0][0])
  assert.equal(calls[1][1], value); assert.equal(calls[1][2], '3'); assert.equal(calls[1][3], 'same-request-key')
})
