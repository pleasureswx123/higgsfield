import request from '@/utils/request'

export const createExchangeRate = (data, key) =>
  request({
    url: '/api/admin/v1/exchange-rate-versions',
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const publishExchangeRate = (id, data, key) =>
  request({
    url: `/api/admin/v1/exchange-rate-versions/${encodeURIComponent(id)}/publish`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })

export const listExchangeRates = (params, signal) =>
  request({ url: '/api/admin/v1/exchange-rate-versions', params, signal })

export const endPriceActivation = (id, data, key, signal) =>
  request({
    businessErrorDetails: true, skipErrorMessage: true,
    url: `/api/admin/v1/price-activations/${encodeURIComponent(id)}/end`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
    signal,
  })

export const publishPrice = (id, data, key, signal) =>
  request({
    businessErrorDetails: true, skipErrorMessage: true,
    url: `/api/admin/v1/price-versions/${encodeURIComponent(id)}/publish`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
    signal,
  })

export const simulatePrice = (id, data, signal) =>
  request({
    url: `/api/admin/v1/price-versions/${encodeURIComponent(id)}/simulate`,
    method: 'post',
    data,
    signal,
    headers: { repeatSubmit: false },
  })

export const createPriceSource = (data, key) =>
  request({
    url: '/api/admin/v1/price-sources',
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })

export const getPriceSource = (id, signal) =>
  request({ url: `/api/admin/v1/price-sources/${encodeURIComponent(id)}`, signal })

export const downloadPriceSource = (id, signal) =>
  request({ url: `/api/admin/v1/price-sources/${encodeURIComponent(id)}/attachment/download`,
    responseType: 'blob', signal })

export const createPriceVersion = (data, key) =>
  request({
    url: '/api/admin/v1/price-versions',
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const updatePriceVersion = (id, data, key) =>
  request({
    url: `/api/admin/v1/price-versions/${encodeURIComponent(id)}`,
    method: 'patch',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })

export const createPriceBook = (data, key) =>
  request({
    url: '/api/admin/v1/price-books',
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })

export const listPriceBooks = (params, signal) =>
  request({ url: '/api/admin/v1/price-books', params, signal })
export const listPriceVersions = (params, signal) =>
  request({ url: '/api/admin/v1/price-versions', params, signal })
export const getPriceVersion = (id, signal) =>
  request({ url: `/api/admin/v1/price-versions/${encodeURIComponent(id)}`, signal })
export const listPriceHistory = (id, params, signal) =>
  request({ url: `/api/admin/v1/price-versions/${encodeURIComponent(id)}/history`, params, signal })
