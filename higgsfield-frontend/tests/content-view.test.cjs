const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const output = {}
runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/utils/contentView.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
  { exports: output, Intl, Date, Map, Number, Math })

test('上海跨日分组保留当前页每条记录、字符串大整数和组内顺序', () => {
  const rows = [
    { id: '9007199254740993', createTime: '2026-10-27T16:00:00Z' },
    { id: '2', createTime: '2026-10-27T15:59:59Z' },
    { id: '3', createTime: '2026-10-27T17:00:00Z' },
    { id: '4', createTime: '无日期' },
  ]
  const groups = output.groupContentByDate(rows, true)
  assert.equal(groups.length, 3)
  assert.equal(groups[0].key, '2026-10-28'); assert.equal(groups[1].key, '2026-10-27')
  assert.equal(groups[0].rows[0], rows[0]); assert.equal(groups[0].rows[1], rows[2])
  assert.equal(groups[2].label, '日期未知')
  assert.equal(groups.reduce((sum, group) => sum + group.rows.length, 0), rows.length)
  assert.equal(output.groupContentByDate(rows, false)[0].rows, rows)
  assert.equal(output.groupContentByDate([], true).length, 0)
})
test('卡片尺寸有界递增且默认值保留原200像素基线', () => {
  assert.equal(output.contentCardWidth(), 200)
  assert.equal(output.contentCardWidth(NaN), 200)
  assert.equal(output.contentCardWidth(-99), output.contentCardWidth(1))
  assert.equal(output.contentCardWidth(99), output.contentCardWidth(8))
  for (let size = 2; size <= 8; size++) assert.ok(output.contentCardWidth(size) > output.contentCardWidth(size - 1))
})

 test('画廊完整行铺满，单张及不足尾行不放大', () => {
  const widths = output.galleryCardWidths([1.78, 1, 2.35, 1.5], 1224, 260)
  assert.ok(Math.abs(widths.slice(0, 3).reduce((a, b) => a + b, 0) + 12 - 1224) < 0.01)
  assert.equal(widths[3], 392)
  assert.equal(output.galleryCardWidths([1.5], 1700, 260)[0], 392)
  assert.ok(output.galleryCardWidths([2], 300, 260)[0] <= 300)
 })
