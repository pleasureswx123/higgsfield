import request from '@/utils/request'

const root = '/api/admin/v1/reconciliations'
export const downloadReconciliation = (id, signal) => request({
  url: `${root}/${encodeURIComponent(id)}/attachment/download`, responseType: 'blob', signal })
export const createReconciliation = (data, key) => request({ url: root, method: 'post', data,
  headers: { 'Idempotency-Key': key, repeatSubmit: false } })
export const listReconciliations = (params, signal) => request({ url: root, params, signal })
export const getReconciliation = (id, signal) => request({ url: `${root}/${encodeURIComponent(id)}`, signal })
export const listReconciliationLines = (id, params, signal) =>
  request({ url: `${root}/${encodeURIComponent(id)}/lines`, params, signal })

export const changeReconciliationLine = (id, action, data, key) => {
  if (!['match', 'confirm', 'resolve'].includes(action)) throw new Error('不支持的对账操作')
  return request({ url: `/api/admin/v1/reconciliation-lines/${encodeURIComponent(id)}/${action}`,
    method: 'post', data, headers: { 'Idempotency-Key': key, repeatSubmit: false } })
}
