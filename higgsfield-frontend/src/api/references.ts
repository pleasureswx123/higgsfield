import { request } from './client'
export interface ReferenceCandidate {
  kind: 'asset' | 'element'
  id: string
  projectId: string
  displayName: string
  allowedMediaRoles: string[]
  assetVersionIds: string[]
  elementRevisionId?: string
  primaryAssetVersionId?: string | null
}
export interface ReferenceUpdate {
  elementRevisionId: string
  state: 'current' | 'updated' | 'unavailable'
  candidate?: ReferenceCandidate
}
export const checkReferenceUpdates = (projectId: string, elementRevisionIds: string[], signal: AbortSignal) =>
  request<{ code: number; data: { items: ReferenceUpdate[] } }>({
    url: '/api/v1/references/updates', method: 'post', data: { projectId, elementRevisionIds }, signal,
  })
export const searchReferences = (
  params: {
    projectId: string
    q: string
    kind?: 'asset' | 'element'
    elementId?: string
    pageNum: number
    pageSize: number
  },
  signal?: AbortSignal,
) =>
  request<{ code: number; rows: ReferenceCandidate[]; total: number }>({
    url: '/api/v1/references/search',
    params,
    signal,
  })
