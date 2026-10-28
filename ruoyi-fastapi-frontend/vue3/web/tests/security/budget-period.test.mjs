import assert from 'node:assert/strict'
import test from 'node:test'
import { budgetPeriodPayload } from '../../src/utils/budgetPeriod.js'

test('月度周期按业务时区跨年及夏令时，金额不丢精度', () => {
  const budget = { cycleKind: 'monthly', businessTimezone: 'Asia/Shanghai' }
  const form = { month: '2026-12', amount: '99999999999999.1234567890', reason: ' 初始化 ' }
  const value = budgetPeriodPayload(budget, undefined, form)
  assert.equal(Date.parse(value.periodStart), Date.parse('2026-11-30T16:00:00Z'))
  assert.equal(Date.parse(value.periodEnd), Date.parse('2026-12-31T16:00:00Z'))
  assert.equal(value.limitAmount, form.amount)
  assert.equal(value.reason, '初始化')
  const dst = budgetPeriodPayload({ ...budget, businessTimezone: 'America/New_York' }, undefined, { ...form, month: '2026-03' })
  assert.equal(Date.parse(dst.periodStart), Date.parse('2026-03-01T05:00:00Z'))
  assert.equal(Date.parse(dst.periodEnd), Date.parse('2026-04-01T04:00:00Z'))
})

test('总额周期无结束时间，调整传总额度和原版本，拒绝非法金额', () => {
  const budget = { cycleKind: 'total', businessTimezone: 'Asia/Shanghai' }
  const form = { start: '2026-10-28 12:00:00', amount: '0', reason: '清零额度' }
  const value = budgetPeriodPayload(budget, undefined, form)
  assert.equal(value.periodEnd, null)
  assert.equal(Date.parse(value.periodStart), Date.parse('2026-10-28T04:00:00Z'))
  assert.deepEqual(budgetPeriodPayload(budget, { revision: '9007199254740993' }, form), { revision: '9007199254740993', newLimit: '0', reason: '清零额度' })
  for (const amount of ['-1', '1e3', '01', '0.00000000001', '100000000000000']) assert.throws(() => budgetPeriodPayload(budget, undefined, { ...form, amount }))
  assert.throws(() => budgetPeriodPayload(budget, undefined, { ...form, reason: ' ' }))
})
