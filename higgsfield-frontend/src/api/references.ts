import { request } from './client'
export interface ReferenceCandidate {
  kind: 'asset' | 'element'
  id: string
  projectId: string
  displayName: string
  alias?: string | null
  category?: string | null
  byteSize?: string | null
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
    mediaType?: 'image' | 'video'
    category?: 'character' | 'scene' | 'prop' | 'other'
    source?: 'uploaded' | 'generated'
    recent?: boolean
    includeEmptyElements?: boolean
    elementScope?: 'project' | 'mine' | 'folder'
    folderId?: string
    sort?: 'newest' | 'oldest' | 'name'
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
