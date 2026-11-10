import test from 'node:test'
import assert from 'node:assert/strict'
import { billingChartPoints, sumBillingAmounts, billingAnalysisData } from '../../src/utils/billingCharts.js'

test('饼图排除零费用，散点图排除未完整计价的人员', () => {
  const rows = [
    {displayName:'甲',userName:'a',totalKnownAmount:'12.5',unknownCount:'0',imageTaskCount:'3',videoTaskCount:'2'},
    {displayName:'乙',totalKnownAmount:'0',unknownCount:'1',imageTaskCount:'1',videoTaskCount:'0'},
    {displayName:'丙',totalKnownAmount:'2',unknownCount:'1',imageTaskCount:'1',videoTaskCount:'1'},
  ]
  assert.equal(billingAnalysisData(rows, 'share').length, 2)
  const points = billingAnalysisData(rows, 'relationship')
  assert.equal(points.length, 1)
  assert.deepEqual(points[0].value, [5, 12.5])
  assert.equal(points[0].name, '甲（a）')
  assert.deepEqual(billingAnalysisData([], 'share'), [])
})

test('日期图表包含结束当天', () => {
  assert.deepEqual(billingChartPoints([], 'day', ['2026-11-08', '2026-11-09']).map(p => p.groupKey), ['2026-11-08', '2026-11-09'])
})

test('金额合计保持十进制精度', () => {
  assert.equal(sumBillingAmounts([{totalKnownAmount:'0.1000000001'}, {totalKnownAmount:'0.2'}]), '0.3000000001')
})
test('日期补零且结束边界不包含', () => {
  const rows = [{groupKey:'2026-11-02', totalKnownAmount:'3', unknownCount:'1'}]
  const points = billingChartPoints(rows, 'day', ['2026-11-01 00:00:00','2026-11-03 00:00:00'])
  assert.equal(points.length, 2)
  assert.equal(points[0].totalKnownAmount, '0.0000000000')
  assert.equal(points[1], rows[0])
})
test('跨年周从周一开始，月份按日历分组', () => {
  const range = ['2026-12-31 12:00:00','2027-01-04 00:00:00']
  assert.deepEqual(billingChartPoints([], 'week', range).map(p => p.groupKey), ['2026-12-28'])
  assert.deepEqual(billingChartPoints([], 'month', range).map(p => p.groupKey), ['2026-12','2027-01'])
})
test('人员按费用排序且不改原数组', () => {
  const rows = [{totalKnownAmount:'2'}, {totalKnownAmount:'10'}]
  assert.equal(billingChartPoints(rows, 'user', [])[0], rows[1])
  assert.equal(rows[0].totalKnownAmount, '2')
})
