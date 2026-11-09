import { toRfc3339 } from './time.js'

/** 费用创建时间使用上海时间输入，接口区间为左闭右开。 */
export function billingTimeWindow(range) {
  if (!range || range.length === 0) return {}
  if (!Array.isArray(range) || range.length !== 2 || range.some((value) => !value))
    throw new Error('请选择完整的起止时间')
  const datesOnly = range.every(value => /^\d{4}-\d{2}-\d{2}$/.test(value))
  const from = toRfc3339(datesOnly ? `${range[0]} 00:00:00` : range[0], { timezoneName: 'Asia/Shanghai' })
  const end = toRfc3339(datesOnly ? `${range[1]} 00:00:00` : range[1], { timezoneName: 'Asia/Shanghai' })
  // 日期选择包含结束日；接口仍使用左闭右开区间，兼容原有精确时间调用。
  const to = datesOnly ? new Date(Date.parse(end) + 86400000).toISOString() : end
  const duration = Date.parse(to) - Date.parse(from)
  if (!Number.isFinite(duration) || duration <= 0 || duration > 366 * 86400000)
    throw new Error('查询时间须递增且不超过366天')
  return { from, to }
}
