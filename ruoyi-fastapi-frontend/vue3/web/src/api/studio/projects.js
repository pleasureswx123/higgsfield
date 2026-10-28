import request from '@/utils/request'

const projectPath = (id) => `/api/v1/projects/${encodeURIComponent(id)}`
export const listStudioProjects = (params) => request({ url: '/api/v1/projects', params })
export const getProjectMembers = (id, params) =>
  request({ url: `${projectPath(id)}/members`, params })
export const getProjectRoles = (id) => request({ url: `${projectPath(id)}/roles` })
export const findProjectCandidate = (id, account) =>
  request({ url: `${projectPath(id)}/member-candidates`, params: { account } })
export const addProjectMember = (id, data, key) =>
  request({
    url: `${projectPath(id)}/members`,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const updateProjectMember = (id, member, roleId, key) =>
  request({
    url: `${projectPath(id)}/members/${member.userId}`,
    method: 'patch',
    data: { revision: member.revision, roleId },
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
export const removeProjectMember = (id, member, key) =>
  request({
    url: `${projectPath(id)}/members/${member.userId}`,
    method: 'delete',
    params: { revision: member.revision },
    headers: { 'Idempotency-Key': key, repeatSubmit: false },
  })
