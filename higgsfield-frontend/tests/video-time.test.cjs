const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const output = {}
runInNewContext(ts.transpileModule(readFileSync('src/utils/videoTime.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: output })
test('视频时间支持零秒、分钟边界和毫秒时间码', () => {
  assert.equal(output.formatVideoTime(0), '00:00')
  assert.equal(output.formatVideoTime(61.456), '01:01')
  assert.equal(output.formatVideoTime(3723.456, true), '01:02:03:456')
  assert.equal(output.formatVideoTime(-1), '00:00')
})
