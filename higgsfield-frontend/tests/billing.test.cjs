const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const exportsForTest = {}
const source = readFileSync(require('node:path').join(__dirname, '../src/utils/billing.ts'), 'utf8')
runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: exportsForTest })

test('金额显示保留高精度，未知值不转换为零', () => {
  const format = exportsForTest.formatBillingDecimal
  assert.equal(format('9007199254740993.1234567890'), '9007199254740993.123456789')
  assert.equal(format('12.3930000000'), '12.393')
  assert.equal(format('100'), '100')
  assert.equal(format('0.0000000000'), '0')
  for (const value of [null, undefined, '', 'NaN', '1e3']) assert.equal(format(value), '待确认')
})

test('超额预算保留负号且不丢精度', () => {
  assert.equal(exportsForTest.formatBudgetDecimal('-0.0000000001'), '-0.0000000001')
  assert.equal(exportsForTest.formatBudgetDecimal('-9007199254740993.10'), '-9007199254740993.1')
  assert.equal(exportsForTest.formatBudgetDecimal('-0.000'), '0')
})
