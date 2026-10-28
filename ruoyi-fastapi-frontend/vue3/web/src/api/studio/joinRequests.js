import request from '@/utils/request'
export const listJoinRequests = (projectId, params, signal) => request({
  url: `/api/admin/v1/projects/${encodeURIComponent(projectId)}/join-requests`, params, signal,
})
export const reviewJoinRequest = (id, data, key, signal) => request({
  url: `/api/admin/v1/join-requests/${encodeURIComponent(id)}/review`, method: 'post', data, signal,
  businessErrorDetails: true,
  skipErrorMessage: true,
  headers: { 'Idempotency-Key': key, repeatSubmit: false },
})
