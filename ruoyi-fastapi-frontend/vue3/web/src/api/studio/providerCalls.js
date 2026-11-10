import request from '@/utils/request'
export const listProviderCalls = (params, signal) => request({ url: '/api/admin/v1/provider-calls', params, signal })
export const getProviderCall = (id, signal) => request({ url: `/api/admin/v1/provider-calls/${encodeURIComponent(id)}`, signal })
export const listCallTasks = (params, signal) => request({ url: '/api/admin/v1/provider-calls/tasks', params, signal })
export const getTaskCalls = (id, signal) => request({ url: `/api/admin/v1/provider-calls/tasks/${encodeURIComponent(id)}/process`, signal })
