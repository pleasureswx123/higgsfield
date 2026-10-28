const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), geometry = {}
runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/utils/commentAnnotation.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: geometry })
test('图片缩放和偏移正确归一化，越界捕获夹到边缘，零尺寸拒绝', () => {
  const rect = { left: 100, top: 200, width: 400, height: 200 }
  assert.equal(JSON.stringify(geometry.imagePoint(300, 250, rect)), JSON.stringify({ x: .5, y: .25 }))
  assert.equal(JSON.stringify(geometry.imagePoint(-10, 999, rect)), JSON.stringify({ x: 0, y: 1 }))
  assert.equal(geometry.imagePoint(1, 1, { ...rect, width: 0 }), undefined)
})
test('矩形支持反向拖动、记录原图尺寸并拒绝零面积和不合法坐标', () => {
  const result = geometry.buildAnnotation('rect', [{ x: .8, y: .9 }, { x: .2, y: .1 }], '#AABBCC', 1920, 1080)
  assert.equal(result.geometry.x, .2); assert.equal(result.geometry.y, .1)
  assert.equal(result.sourceWidth, 1920); assert.equal(result.sourceHeight, 1080); assert.equal(result.color, '#aabbcc')
  assert.equal(geometry.buildAnnotation('rect', [{ x: 0, y: 0 }, { x: 0, y: 1 }], '#ff0000', 100, 100), undefined)
  assert.equal(geometry.buildAnnotation('point', [{ x: NaN, y: 0 }], '#ff0000', 100, 100), undefined)
})
test('路径点数限制为2至256且复制坐标，不能通过副本修改输入', () => {
  const points = [{ x: 0, y: 0 }, { x: 1, y: 1 }]
  const result = geometry.buildAnnotation('path', points, '#ff0000', 100, 100)
  result.geometry.points[0].x = .5; assert.equal(points[0].x, 0)
  assert.equal(geometry.buildAnnotation('path', points.slice(0, 1), '#ff0000', 100, 100), undefined)
  assert.equal(geometry.buildAnnotation('path', Array(257).fill(points[0]), '#ff0000', 100, 100), undefined)
})
