import request from '@/utils/request'

const base = '/api/admin/v1'
export const listProviderConnections = (params) =>
  request({ url: `${base}/provider-connections`, params })
export const getProviderConnection = (id) => request({ url: `${base}/provider-connections/${id}` })
export const listProviderAccounts = (params) =>
  request({ url: `${base}/provider-accounts`, params })
export const saveProviderConnection = (id, data, key) =>
  request({
    url: `${base}/provider-connections${id ? `/${id}` : ''}`,
    method: id ? 'patch' : 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const createProviderAccount = (data, key) =>
  request({
    url: `${base}/provider-accounts`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
