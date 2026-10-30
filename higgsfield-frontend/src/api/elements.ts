import { request } from './client'

export type ElementCategory = 'character' | 'scene' | 'prop' | 'other'
export type WorkStatus = 'none' | 'working' | 'review' | 'approved' | 'rejected'
export interface ElementRecord {
  media?: ElementMedia[]
  performerName?: string
  projectName?: string
  description?: string
  label?: string
  revisionNo?: number
  id: string
  projectId: string
  spaceId: string
  name: string
  alias: string
  category: ElementCategory
  workStatus: WorkStatus
  revision: string
  currentRevisionId: string
  performerId: string | null
  folderId: string | null
  allowedActions?: string[]
  createTime: string
}
export interface ElementMedia {
  assetVersionId: string
  ordinal: number
  isPrimary: boolean
}
export interface PropertyValue {
  definitionId: string
  definitionVersion: number
  value: string | string[] | null
}
export interface PropertyDefinition {
  id: string
  propertyKey: string
  versionNo: number
  name: string
  valueType: 'text' | 'multi_select' | 'single_select'
  options: string[]
}
export interface PropertySnapshot extends PropertyValue {
  propertyKey: string
  name: string
  valueType: PropertyDefinition['valueType']
  options: string[]
}
export interface ElementRevision {
  id: string
  elementId: string
  revisionNo: number
  description: string
  label: string
  labelRevision: string
  media: ElementMedia[]
  propertyValues: PropertyValue[]
  propertySnapshot: PropertySnapshot[]
}
export interface ElementDetail {
  element: ElementRecord
  currentRevision: ElementRevision
}
export interface ElementFields {
  name: string
  alias: string
  category: ElementCategory
  workStatus: WorkStatus
  performerId: string | null
  description: string
  label: string
  media: ElementMedia[]
  propertyValues: PropertyValue[]
}
export interface RecycledElement {
  id: string
  targetId: string
  name: string
  revision: string
  restoreUntil: string
  remainingDays: number
  canRestore: boolean
}
interface Result<T> {
  code: number
  data: T
}
interface Page<T> {
  code: number
  rows: T[]
  total: number
  hasNext: boolean
}
export const listElements = (
  projectId: string | undefined,
  params: {
    pageNum: number
    pageSize?: number
    q: string
    category?: ElementCategory
    folderId?: string
    statusGroup?: 'active' | 'drafts'
    workStatus?: WorkStatus
    scope?: 'project' | 'mine'
    mineFilter?: 'all' | 'created' | 'favorites'
  },
  signal: AbortSignal,
) =>
  request<Page<ElementRecord>>({
    url: '/api/v1/elements',
    params: { ...params, projectId },
    signal,
  })
export const readElement = (id: string, signal?: AbortSignal) =>
  request<Result<ElementDetail>>({ url: `/api/v1/elements/${id}`, signal })
export const createElement = (projectId: string, fields: ElementFields, key: string) =>
  request<Result<ElementDetail>>({
    url: '/api/v1/elements',
    method: 'POST',
    data: { ...fields, projectId },
    headers: { 'Idempotency-Key': key },
  })
export const saveElement = (id: string, revision: string, fields: ElementFields, key: string) =>
  request<Result<ElementDetail>>({
    url: `/api/v1/elements/${id}/save`,
    method: 'POST',
    data: { ...fields, revision },
    headers: { 'Idempotency-Key': key },
  })
export const listProperties = (projectId: string, pageNum: number, signal: AbortSignal) =>
  request<Page<PropertyDefinition>>({
    url: `/api/v1/projects/${projectId}/property-definitions`,
    params: { pageNum, pageSize: 100 },
    signal,
  })
export const listRevisions = (id: string, pageNum: number, signal: AbortSignal) =>
  request<Page<ElementRevision>>({
    url: `/api/v1/elements/${id}/revisions`,
    params: { pageNum, pageSize: 30 },
    signal,
  })
export const listElementTrash = (projectId: string, pageNum: number, signal: AbortSignal) =>
  request<Page<RecycledElement>>({
    url: `/api/v1/projects/${projectId}/trash`,
    params: { kind: 'element', pageNum, pageSize: 30 },
    signal,
  })
export const recycleElement = (id: string, revision: string, restore: boolean, key: string) =>
  request<Result<ElementRecord>>({
    url: `/api/v1/elements/${id}${restore ? '/restore' : ''}`,
    method: restore ? 'POST' : 'DELETE',
    ...(restore ? { data: { revision } } : { params: { revision } }),
    headers: { 'Idempotency-Key': key },
  })

export const copyElement = (
  id: string,
  data: { targetProjectId: string; sourceRevisionId: string; name: string; alias: string },
  key: string,
) =>
  request<Result<ElementRecord>>({
    url: `/api/v1/elements/${id}/copy`,
    method: 'POST',
    data,
    headers: { 'Idempotency-Key': key },
  })

export interface PropertyDefinitionFields {
  name: string
  valueType: 'text' | 'multi_select'
  options: string[]
}
export const createProperty = (
  projectId: string,
  fields: PropertyDefinitionFields & { propertyKey: string },
  key: string,
) =>
  request<Result<PropertyDefinition>>({
    url: `/api/v1/projects/${projectId}/property-definitions`,
    method: 'POST',
    data: fields,
    headers: { 'Idempotency-Key': key },
  })
export const versionProperty = (id: string, fields: PropertyDefinitionFields, key: string) =>
  request<Result<PropertyDefinition>>({
    url: `/api/v1/property-definitions/${id}/versions`,
    method: 'POST',
    data: fields,
    headers: { 'Idempotency-Key': key },
  })

export const moveElement = (
  id: string,
  data: { revision: string; folderId: string | null },
  key: string,
  signal?: AbortSignal,
) =>
  request<Result<ElementRecord>>({
    url: `/api/v1/elements/${id}/move`,
    method: 'POST',
    data,
    headers: { 'Idempotency-Key': key },
    signal,
  })
