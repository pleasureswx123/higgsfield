import request from '@/utils/request'
export const createModelVersion = (id, data, key) =>
  request({
    url: `/api/admin/v1/model-profiles/${encodeURIComponent(id)}/versions`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const updateModelVersion = (id, data, key) =>
  request({
    url: `/api/admin/v1/model-profile-versions/${encodeURIComponent(id)}`,
    method: 'patch',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const createModelVariant = (id, data, key) =>
  request({
    url: `/api/admin/v1/model-profile-versions/${encodeURIComponent(id)}/variants`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const createModelProfile = (data, key) =>
  request({
    url: '/api/admin/v1/model-profiles',
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const changeModelVersionState = (id, action, data, key) => {
  if (!['verify', 'publish', 'disable'].includes(action)) throw new Error('无效模型状态操作')
  return request({
    url: `/api/admin/v1/model-profile-versions/${encodeURIComponent(id)}/${action}`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
}
export const listModels = (params, signal) =>
  request({ url: '/api/admin/v1/model-profiles', params, signal })
export const listModelVersions = (id, params, signal) =>
  request({
    url: `/api/admin/v1/model-profiles/${encodeURIComponent(id)}/versions`,
    params,
    signal,
  })
export const getModelVersion = (id, signal) =>
  request({ url: `/api/admin/v1/model-profile-versions/${encodeURIComponent(id)}`, signal })
export const listModelVariants = (id, params, signal) =>
  request({
    url: `/api/admin/v1/model-profile-versions/${encodeURIComponent(id)}/variants`,
    params,
    signal,
  })
