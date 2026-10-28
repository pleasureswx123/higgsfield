import assert from 'node:assert/strict'
import test from 'node:test'
import { billingTimeWindow } from '../../src/utils/billingQuery.js'
import { setUserTimezone } from '../../src/utils/time.js'

test('费用时间范围固定上海时间，不受显示时区影响，结束时刻不自动扩展', () => {
  setUserTimezone('America/New_York')
  try {
    const result = billingTimeWindow(['2026-10-01 00:00:00', '2026-10-28 12:30:00'])
    assert.equal(Date.parse(result.from), Date.parse('2026-09-30T16:00:00Z'))
    assert.equal(Date.parse(result.to), Date.parse('2026-10-28T04:30:00Z'))
    assert.deepEqual(billingTimeWindow(null), {})
    assert.deepEqual(billingTimeWindow([]), {})
    for (const range of [
      ['2026-10-01 00:00:00'],
      ['2026-10-01 00:00:00', '2026-10-01 00:00:00'],
      ['2026-10-01 00:00:00', '2026-09-30 00:00:00'],
      ['2025-01-01 00:00:00', '2026-01-03 00:00:00'],
      ['非法日期', '2026-10-28 00:00:00'],
    ]) assert.throws(() => billingTimeWindow(range))
  } finally { setUserTimezone('auto') }
})
