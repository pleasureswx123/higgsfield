import { toRfc3339 } from './time.js'

export function reconciliationInput(form) {
  const accountId = form.accountId.trim()
  if (!/^[1-9][0-9]{0,18}$/.test(accountId) || BigInt(accountId) > 9223372036854775807n)
    throw new Error('请输入有效供应商账号ID')
  if (!Array.isArray(form.period) || form.period.length !== 2 || form.period.some(value => !value))
    throw new Error('请选择完整账期')
  const periodStart = toRfc3339(form.period[0], { timezoneName: 'Asia/Shanghai' })
  const periodEnd = toRfc3339(form.period[1], { timezoneName: 'Asia/Shanghai' })
  if (!Number.isFinite(Date.parse(periodStart)) || !Number.isFinite(Date.parse(periodEnd)) || Date.parse(periodEnd) <= Date.parse(periodStart))
    throw new Error('账期终点必须晚于起点')
  return { accountId, periodStart, periodEnd }
}
