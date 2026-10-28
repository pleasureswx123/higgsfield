/** 素材日期选择采用上海自然日，接口结束时间为次日零点。 */
export function libraryWindow(dates: string[] | null): { from?: string; to?: string } {
  if (!dates?.length) return {}
  if (dates.length !== 2) throw new Error('请选择完整的创建日期范围')
  const instants = dates.map(value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('日期格式无效')
    const instant = Date.parse(`${value}T00:00:00+08:00`)
    if (!Number.isFinite(instant) || new Date(instant + 28800000).toISOString().slice(0, 10) !== value) throw new Error('日期无效')
    return instant
  })
  if (instants[0]! > instants[1]!) throw new Error('结束日期不能早于开始日期')
  return { from: new Date(instants[0]!).toISOString(), to: new Date(instants[1]! + 86400000).toISOString() }
}
