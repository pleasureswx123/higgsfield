import request from '@/utils/request'
export const listGovernedProjects = (params, signal) =>
  request({ url: '/api/admin/v1/projects', params, signal })
export const governProject = (id, data, key) =>
  request({
    url: `/api/admin/v1/projects/${encodeURIComponent(id)}/governance`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
