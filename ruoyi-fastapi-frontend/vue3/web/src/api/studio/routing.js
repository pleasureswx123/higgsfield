import request from '@/utils/request'

export const getRouting = (id, signal) =>
  request({
    url: `/api/admin/v1/project-provider-configs/${encodeURIComponent(id)}`,
    signal,
  })
export const saveRouting = (id, data, key) =>
  request({
    url: `/api/admin/v1/project-provider-configs/${encodeURIComponent(id)}`,
    method: 'put',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
