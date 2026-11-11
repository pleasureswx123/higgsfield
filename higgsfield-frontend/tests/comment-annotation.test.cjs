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

// 缩放和平移不能改变同一原图位置对应的归一化坐标。
test('横图与竖图在缩放、拖动、复位后标注仍对应同一个原图位置', () => {
  for (const [w, h] of [[2048, 1152], [1152, 2048]]) {
    for (const [zoom, x, y] of [[1, 0, 0], [1.6, -150, 90], [.6, 0, 0], [1, 0, 0]]) {
      const box = geometry.annotationBounds(1543, 1004, w, h, zoom, x, y)
      const point = geometry.imagePoint(box.left + box.width * .32, box.top + box.height * .74, box)
      assert.ok(Math.abs(point.x - .32) < 1e-12)
      assert.ok(Math.abs(point.y - .74) < 1e-12)
      assert.ok(Math.abs(box.width / box.height - w / h) < 1e-12)
    }
  }
  const moved = geometry.annotationBounds(1600, 1000, 2000, 1000, 2, 100, -50)
  assert.equal(JSON.stringify(moved), JSON.stringify({ left: -700, top: -350, width: 3200, height: 1600 }))
})
