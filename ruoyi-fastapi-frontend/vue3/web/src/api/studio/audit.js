import request from '@/utils/request'

export const listAuditLogs = (params, signal) =>
  request({ url: '/api/admin/v1/audit-logs', params, signal })
