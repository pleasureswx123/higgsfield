import request from '@/utils/request'
export const createBudgetPeriod = (id, data, key) =>
  request({
    url: `/api/admin/v1/budgets/${encodeURIComponent(id)}/periods`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const adjustBudgetLimit = (id, data, key) =>
  request({
    url: `/api/admin/v1/budget-periods/${encodeURIComponent(id)}/adjust-limit`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })

export const createBudget = (data, key) =>
  request({
    url: '/api/admin/v1/budgets',
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const updateBudget = (id, data, key) =>
  request({
    url: `/api/admin/v1/budgets/${encodeURIComponent(id)}`,
    method: 'put',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const listBudgets = (params, signal) =>
  request({ url: '/api/admin/v1/budgets', params, signal })
export const listBudgetPeriods = (id, params, signal) =>
  request({ url: `/api/admin/v1/budgets/${encodeURIComponent(id)}/periods`, params, signal })
export const listBudgetLedger = (id, params, signal) =>
  request({ url: `/api/admin/v1/budget-periods/${encodeURIComponent(id)}/ledger`, params, signal })
