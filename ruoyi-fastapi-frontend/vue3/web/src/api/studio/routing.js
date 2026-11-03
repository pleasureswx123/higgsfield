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

// 全平台默认配置沿用项目配置的并发版本和幂等写入协议。
export const getPlatformRouting = () => request({ url: '/api/admin/v1/platform-provider-configs' })
export const savePlatformRouting = (data, key) => request({
  url: '/api/admin/v1/platform-provider-configs', method: 'put', data,
  businessErrorDetails: true,
  headers: { 'Idempotency-Key': key, repeatSubmit: false },
})
