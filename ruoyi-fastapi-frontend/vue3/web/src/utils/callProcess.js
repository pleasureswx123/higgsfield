// 仅折叠连续的进度查询，保留提交、重试等真实先后顺序。
export function assetQueryStatus(row) {
  if (row.operation === 'upload') return ({ Uploaded: '上传成功', Pending: '等待上传', Sending: '上传中', RequestFailed: '上传请求失败' })[row.assetQuery?.state] || '上传结果未确认'
  if (row.operation === 'register') return ({ Registered: '注册成功（待检查可用状态）', Pending: '等待注册', Sending: '注册中', RequestFailed: '注册请求失败' })[row.assetQuery?.state] || '注册结果未确认'
  return ({ Active: '素材可用', Processing: '素材处理中', Failed: '素材处理失败', Expired: '素材已过期', Deleted: '素材已删除' })[row.assetQuery?.state] || '素材状态未确认'
}

export function groupCallProcess(rows) {
  const groups = []
  for (const row of rows) {
    const previous = groups.at(-1)
    if (row.operation === 'video_poll' && previous?.operation === 'video_poll') previous.calls.push(row)
    else groups.push({ id: row.id, operation: row.operation, calls: [row] })
  }
  return groups
}

export function callTaskState(row) {
  if (row.orchestrationState === '3' || row.upstreamState === '6') return '受理或结果待核查'
  if (row.upstreamState === '4') return '生成失败'
  if (row.upstreamState === '5') return '已取消'
  if (row.upstreamState === '3') return '供应商生成成功'
  if (row.orchestrationState === '6') return '已阻塞'
  return ({ '0': '已受理', '1': '准备素材', '2': '提交生成', '4': '等待生成', '5': '执行已结束' })[row.orchestrationState] || '状态待核查'
}

export function executionDuration(row) {
  if (!row.finishedAt) return '尚未结束'
  const milliseconds = Date.parse(row.finishedAt) - Date.parse(row.createdAt)
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return '未记录'
  const seconds = Math.ceil(milliseconds / 1000)
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}
