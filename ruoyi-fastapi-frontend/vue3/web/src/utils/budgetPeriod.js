import { toRfc3339 } from './time.js'

export function budgetPeriodPayload(budget, period, form) {
  if (!/^(0|[1-9]\d{0,13})(\.\d{1,10})?$/.test(form.amount))
    throw new Error('额度必须为非负十进制数，最多14位整数和10位小数')
  const reason = form.reason.trim()
  if (!reason || reason.length > 4000) throw new Error('请输入变更原因，最多4000字')
  if (period) return { revision: period.revision, newLimit: form.amount, reason }
  const options = { timezoneName: budget.businessTimezone }
  if (budget.cycleKind === 'monthly') {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(form.month)) throw new Error('请选择预算月份')
    const [year, month] = form.month.split('-').map(Number)
    if (year < 1 || year >= 9999) throw new Error('预算年份超出支持范围')
    const next = `${String(year + (month === 12 ? 1 : 0)).padStart(4, '0')}-${String(month === 12 ? 1 : month + 1).padStart(2, '0')}`
    return {
      periodStart: toRfc3339(`${form.month}-01 00:00:00`, options),
      periodEnd: toRfc3339(`${next}-01 00:00:00`, options),
      limitAmount: form.amount,
      reason,
    }
  }
  if (!form.start) throw new Error('请选择总额预算开始时刻')
  return {
    periodStart: toRfc3339(form.start, options),
    periodEnd: null,
    limitAmount: form.amount,
    reason,
  }
}
