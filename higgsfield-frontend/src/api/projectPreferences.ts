import { request } from './client'

export interface ProjectPreference {
  projectId: string
  isPinned: boolean
  isHidden: boolean
  collectionId: string | null
  orderNum: number
  revision: string
}
export interface ProjectCollection {
  id: string
  name: string
  description: string | null
  color: string | null
  orderNum: number
  revision: string
}
export interface CollectionPage {
  code: number
  rows: ProjectCollection[]
  total: number
  hasNext: boolean
}
export const getProjectCollections = (pageNum = 1, signal?: AbortSignal) =>
  request<CollectionPage>({ url: '/api/v1/project-collections', params: { pageNum, pageSize: 100 }, signal })
export const createProjectCollection = (data: { name: string; orderNum?: number }, key: string, signal?: AbortSignal) =>
  request<{ code: number; data: ProjectCollection }>({ url: '/api/v1/project-collections', method: 'POST', data,
    headers: { 'Idempotency-Key': key }, signal })
export const updateProjectCollection = (id: string, data: { revision: string; name?: string; description?: string | null; color?: string | null; orderNum?: number }, key: string, signal?: AbortSignal) =>
  request<{ code: number; data: ProjectCollection }>({ url: `/api/v1/project-collections/${encodeURIComponent(id)}`, method: 'PATCH', data,
    headers: { 'Idempotency-Key': key }, signal })
export const deleteProjectCollection = (id: string, revision: string, key: string, signal?: AbortSignal) =>
  request<{ code: number; data: { id: string } }>({ url: `/api/v1/project-collections/${encodeURIComponent(id)}`, method: 'DELETE', params: { revision },
    headers: { 'Idempotency-Key': key }, signal })
export const getProjectPreference = (id: string, signal?: AbortSignal) =>
  request<{ code: number; data: ProjectPreference }>({ url: `/api/v1/projects/${encodeURIComponent(id)}/preferences`, signal })
export const putProjectPreference = (id: string, data: Pick<ProjectPreference, 'revision'> & Partial<Pick<ProjectPreference, 'isPinned' | 'isHidden' | 'collectionId' | 'orderNum'>>, key: string, signal?: AbortSignal) =>
  request<{ code: number; data: ProjectPreference }>({ url: `/api/v1/projects/${encodeURIComponent(id)}/preferences`, method: 'PUT', data,
    headers: { 'Idempotency-Key': key }, signal })

