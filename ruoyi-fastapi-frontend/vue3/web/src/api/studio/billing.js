import request from '@/utils/request'

export const getBillingSummary = (params, signal) =>
  request({ url: '/api/admin/v1/usage/summary', params, signal })

export const listBillingEvents = (params, signal) =>
  request({ url: '/api/admin/v1/billing-events', params, signal })
export const getBillingEvent = (id, signal) =>
  request({ url: `/api/admin/v1/billing-events/${encodeURIComponent(id)}`, signal })

export const adjustBillingEvent = (id, data, key, signal) =>
  request({
    url: `/api/admin/v1/billing-events/${encodeURIComponent(id)}/adjustments`,
    businessErrorDetails: true, skipErrorMessage: true, signal,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
