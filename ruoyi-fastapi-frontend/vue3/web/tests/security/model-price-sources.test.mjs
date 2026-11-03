import assert from 'node:assert/strict'
import test from 'node:test'
import { modelPriceSources } from '../../src/utils/modelPriceSources.js'
test('价格依据按精确模型筛选，结构化内容显示中文摘要', () => {
 const rows = [{id:'1',excerpt:'供应商确认 mm-imagen2 输入 5，输出 30'}, {id:'2',excerpt:JSON.stringify({model:'mm-eva-sd-2.5',exchangeRate:'6.69',prices:[{resolution:'480p',withVideo:'42',withoutVideo:'70'}]})}, {id:'3',excerpt:'mm-imagen20'}, {id:'4',excerpt:'未注明模型'}]
 assert.deepEqual(modelPriceSources(rows,'mm-imagen2').map(row=>row.id),['1'])
 const video=modelPriceSources(rows,'mm-eva-sd-2.5')[0]
 assert.ok(!video.label.includes('{'))
 assert.ok(video.description.includes('1 USD = 6.69 CNY'))
 assert.ok(video.description.includes('含参考视频 42'))
 assert.ok(rows[1].excerpt.startsWith('{'))
})
