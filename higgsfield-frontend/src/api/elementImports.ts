import { request } from './client'
import type { PropertyValue } from './elements'

export interface ImportCandidate {
  schemaVersion: 1
  name: string
  alias: string
  category: string
  description: string
  propertyValues: PropertyValue[]
}
export interface ImportRow {
  rowNo: number
  revision: string
  candidate: ImportCandidate
  isSelected: boolean
  state: 'pending' | 'succeeded' | 'failed'
  sourceLocator: { line?: number; sheet?: string; row?: number; paragraph?: number; page?: number }
  issues: { code: string; message: string; field?: string }[]
  elementId: string | null
}
export interface ImportBatch {
  id: string
  projectId: string
  revision: string
  status: 'uploaded' | 'validated' | 'confirmed' | 'finished' | 'failed'
  summary: { total: number; valid: number; invalid: number }
  errors: { message: string }[]
}
interface Result<T> {
  code: number
  data: T
}
const headers = (key: string) => ({ 'Idempotency-Key': key })
export const createElementImport = (
  projectId: string,
  uploadId: string,
  includeProjectName: boolean,
  key: string,
  signal: AbortSignal,
) =>
  request<Result<{ id: string }>>({
    url: '/api/v1/imports/elements',
    method: 'POST',
    data: { projectId, uploadId, includeProjectName, schemaVersion: 1 },
    headers: headers(key),
    signal,
  })
export const readElementImport = (id: string, signal: AbortSignal) =>
  request<Result<ImportBatch>>({ url: `/api/v1/imports/elements/${id}`, signal })
export const listElementImportRows = (id: string, pageNum: number, signal: AbortSignal) =>
  request<{ code: number; rows: ImportRow[]; total: number }>({
    url: `/api/v1/imports/elements/${id}/rows`,
    params: { pageNum, pageSize: 20 },
    signal,
  })
export const editElementImportRow = (
  id: string,
  row: ImportRow,
  key: string,
  signal: AbortSignal,
) =>
  request<Result<ImportRow & { batchRevision: string }>>({
    url: `/api/v1/imports/elements/${id}/rows/${row.rowNo}`,
    method: 'PATCH',
    data: { revision: row.revision, candidate: row.candidate, isSelected: row.isSelected },
    headers: headers(key),
    signal,
  })
export const confirmElementImport = (
  id: string,
  revision: string,
  key: string,
  signal: AbortSignal,
) =>
  request<Result<{ createdCount: number }>>({
    url: `/api/v1/imports/elements/${id}/confirm`,
    method: 'POST',
    data: { revision },
    headers: headers(key),
    signal,
  })
