const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const exported = {}
runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/utils/imageSize.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: exported })
const { imageSize, imageSizeIssue } = exported

test('任务失败的横竖屏 1K 组合在提交前明确提示', () => {
  assert.equal(imageSize('16:9', '1K'), '1024x576')
  for (const ratio of ['16:9', '9:16', '21:9']) assert.match(imageSizeIssue(imageSize(ratio, '1K')), /请选择 2K/)
})

test('像素上下限、自动尺寸与合法 2K 组合', () => {
  for (const size of ['auto', '1024x640', '1024x1024', '2048x1152', '3840x2160']) assert.equal(imageSizeIssue(size), '')
  assert.notEqual(imageSizeIssue('3840x3840'), '')
  for (const ratio of ['1:1', '3:2', '2:3', '16:9', '9:16', '4:3', '3:4', '21:9']) assert.equal(imageSizeIssue(imageSize(ratio, '2K')), '')
})
