// 占比仅使用正的已知费用；关系图排除费用尚未完整确认的人员。
export function billingAnalysisData(rows, kind) {
  return rows.filter(row => kind === 'share' ? Number(row.totalKnownAmount) > 0 :
    Number(row.unknownCount || 0) === 0 && row.imageTaskCount != null && row.videoTaskCount != null)
    .map(row => ({ name: row.userName ? `${row.displayName}（${row.userName}）` : row.displayName,
      value: kind === 'share' ? Number(row.totalKnownAmount) :
        [Number(row.imageTaskCount) + Number(row.videoTaskCount), Number(row.totalKnownAmount)], row }))
}

// 金额卡片使用十进制定点计算；浮点数只用于图表坐标。
export function sumBillingAmounts(rows, field = 'totalKnownAmount') {
  const total = rows.reduce((sum, row) => {
    const [whole, fraction = ''] = String(row[field] || '0').split('.')
    return sum + BigInt(whole) * 10000000000n + BigInt(fraction.padEnd(10, '0').slice(0, 10))
  }, 0n)
  return `${total / 10000000000n}.${String(total % 10000000000n).padStart(10, '0')}`
}

export function billingChartPoints(rows, groupBy, timeRange) {
  if (groupBy === 'user') return [...rows].sort((a, b) => Number(b.totalKnownAmount) - Number(a.totalKnownAmount))
  if (!timeRange?.[0] || !timeRange?.[1]) return rows
  // 使用上海本地日历进行分桶，避免浏览器时区影响周/月边界。
  const datesOnly = timeRange.every(value => /^\d{4}-\d{2}-\d{2}$/.test(value))
  const start = new Date(`${timeRange[0].replace(' ', 'T')}${datesOnly ? 'T00:00:00' : ''}Z`)
  const end = new Date(`${timeRange[1].replace(' ', 'T')}${datesOnly ? 'T00:00:00' : ''}Z`)
  if (datesOnly) end.setUTCDate(end.getUTCDate() + 1)
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || start >= end) return rows
  start.setUTCHours(0, 0, 0, 0)
  if (groupBy === 'week') start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7)
  if (groupBy === 'month') start.setUTCDate(1)
  const indexed = new Map(rows.map(row => [row.groupKey, row]))
  const points = []
  while (start < end && points.length < 367) {
    const key = start.toISOString().slice(0, groupBy === 'month' ? 7 : 10)
    points.push(indexed.get(key) || { groupKey: key, displayName: key, totalKnownAmount: '0.0000000000', unknownCount: '0' })
    if (groupBy === 'month') start.setUTCMonth(start.getUTCMonth() + 1)
    else start.setUTCDate(start.getUTCDate() + (groupBy === 'week' ? 7 : 1))
  }
  return points
}
