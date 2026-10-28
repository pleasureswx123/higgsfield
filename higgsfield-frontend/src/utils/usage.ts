/** 日期筛选按上海自然日处理，结束日期包含当天，接口使用右开区间。 */
export function usageWindow(dates: string[]) {
  if (dates.length !== 2) throw new Error('请选择起止日期')
  const timestamps = dates.map((value) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('日期格式无效')
    const instant = Date.parse(`${value}T00:00:00+08:00`)
    if (
      !Number.isFinite(instant) ||
      new Date(instant + 8 * 3600000).toISOString().slice(0, 10) !== value
    )
      throw new Error('日期无效')
    return instant
  })
  const start = timestamps[0]!,
    end = timestamps[1]! + 86400000
  if (end <= start || end - start > 366 * 86400000) throw new Error('日期范围须递增且不超过366天')
  return { from: new Date(start).toISOString(), to: new Date(end).toISOString() }
}

export function defaultUsageDates(now = new Date()) {
  const today = new Date(now.getTime() + 8 * 3600000).toISOString().slice(0, 10)
  return [`${today.slice(0, 7)}-01`, today]
}
