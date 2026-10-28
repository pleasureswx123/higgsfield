import { request } from './client'
import type { ProjectPreference } from './projectPreferences'
export type ProjectStatus = 'active' | 'paused' | 'archived' | 'pending_delete'
export interface Project {
  id: string
  name: string
  status: ProjectStatus
  revision: string
  createTime: string
  updateTime: string
  currentUserRole: string
  archivedAt: string | null
  spaceId: string | null
  memberCount: number | null
  preference?: ProjectPreference | null
}
export interface ProjectPage {
  code: number
  rows: Project[]
  pageNum: number
  pageSize: number
  total: number
  hasNext: boolean
}
export interface ProjectQuery {
  pageNum: number
  pageSize: number
  q?: string
  status?: ProjectStatus
  sort?: 'created_desc' | 'created_asc' | 'name_asc'
  hidden?: boolean
  pinned?: boolean
  collectionId?: string
}
export const getProjects = (params: ProjectQuery, signal?: AbortSignal) =>
  request<ProjectPage>({ url: '/api/v1/projects', params, signal })
export const getProject = (id: string, signal?: AbortSignal) =>
  request<{ code: number; data: Project }>({
    url: `/api/v1/projects/${encodeURIComponent(id)}`,
    signal,
  })
export const createProject = (name: string, key: string) =>
  request<{ code: number; data: Project }>({
    url: '/api/v1/projects',
    method: 'POST',
    data: { name },
    headers: { 'Idempotency-Key': key },
  })

export const changeProjectLifecycle = (id: string, action: 'archive' | 'restore' | 'rename' | 'pause' | 'resume',
  data: { revision: string; reason?: string; name?: string }, key: string, signal?: AbortSignal) =>
  request<{ code: number; data: Project }>({
    url: `/api/v1/projects/${encodeURIComponent(id)}${action === 'rename' ? '' : `/${action}`}`,
    method: action === 'rename' ? 'PATCH' : 'POST', data,
    headers: { 'Idempotency-Key': key }, signal,
  })
