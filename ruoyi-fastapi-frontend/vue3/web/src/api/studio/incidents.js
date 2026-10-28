import request from '@/utils/request'
export const listIncidents = (params, signal) => request({ url: '/api/admin/v1/generation-incidents', params, signal })
export const getIncident = (id, signal) => request({ url: `/api/admin/v1/generation-incidents/${encodeURIComponent(id)}`, signal })
export const recoverIncident = (id, data, key, signal) => request({
  businessErrorDetails: true, skipErrorMessage: true,
  url: `/api/admin/v1/generation-incidents/${encodeURIComponent(id)}/actions`, method: 'post', data,
  headers: { 'Idempotency-Key': key, repeatSubmit: false }, signal,
})
