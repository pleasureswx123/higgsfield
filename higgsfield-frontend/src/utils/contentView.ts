// 与当前制作端时间展示一致，按上海自然日分组；不改变服务端分页或业务顺序。
const dayFormatter = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' })
export function groupContentByDate<T extends { createTime: string }>(rows: T[], split: boolean) {
  if (!split) return [{ key: 'all', label: '', rows }]
  const groups = new Map<string, { key: string; label: string; rows: T[] }>()
  for (const row of rows) {
    const date = new Date(row.createTime)
    const key = Number.isFinite(date.getTime()) ? dayFormatter.format(date) : 'unknown'
    let group = groups.get(key)
    if (!group) { group = { key, label: key === 'unknown' ? '日期未知' : key, rows: [] }; groups.set(key, group) }
    group.rows.push(row)
  }
  return Array.from(groups.values())
}

export function contentCardWidth(size = 4) {
  const value = Number.isFinite(size) ? Math.max(1, Math.min(8, Math.round(size))) : 4
  return 120 + value * 20
}
