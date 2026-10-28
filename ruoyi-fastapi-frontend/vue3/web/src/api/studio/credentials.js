import request from '@/utils/request'

const base = '/api/admin/v1'
export const listCredentialTestModels = (id, params, signal) =>
  request({ url: `${base}/credential-versions/${encodeURIComponent(id)}/test-models`, params, signal })
export const listTestCostCenters = (params, signal) => request({ url: `${base}/cost-centers`, params, signal })
export const createCredentialTest = (id, data, key) => request({
  url: `${base}/credential-versions/${encodeURIComponent(id)}/tests`, method: 'post', data,
  headers: { 'Idempotency-Key': key, repeatSubmit: false },
})
export const getCredentialTest = (id, signal) =>
  request({ url: `${base}/credential-tests/${encodeURIComponent(id)}`, signal })
export const listCredentialTests = (id, params, signal) =>
  request({ url: `${base}/credential-versions/${encodeURIComponent(id)}/tests`, params, signal })
export const changeCredentialState = (id, action, data, key) =>
  request({
    url: `${base}/credential-versions/${id}/${action}`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const listCredentials = (params) => request({ url: `${base}/credentials`, params })
export const getCredential = (id) => request({ url: `${base}/credentials/${id}` })
export const listCredentialVersions = (id, params) =>
  request({ url: `${base}/credentials/${id}/versions`, params })
export { listProviderAccounts, getProviderConnection } from './providers'
export const saveCredential = (id, data, key) =>
  request({
    url: id ? `${base}/credentials/${id}/versions` : `${base}/credentials`,
    method: 'post',
    data,
    sensitiveRequest: true,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
