import { request, requestBlob } from './client'
import { assetUploadMime, type AssetFileType } from '@/utils/assetFormats'

export interface UploadSession {
  id: string
  state: 'created' | 'uploading' | 'verifying' | 'ready' | 'failed' | 'cancelled' | 'expired'
  partSize: string
  partCount: number
  receivedParts: number[]
  expiresAt: string
}
export type AssetWorkStatus = 'none' | 'working' | 'review' | 'approved' | 'rejected'
export interface Asset {
  workStatus?: AssetWorkStatus
  allowedActions?: string[]
  id: string
  name: string
  mediaType: 'image' | 'video' | 'document'
  currentVersionId: string
  uploaded?: boolean
  revision: string
  file: {
    mimeType: string
    byteSize: string
    width: number | null
    height: number | null
    seconds: string | null
  }
}
export interface RecycledAsset {
  id: string
  targetId: string
  name: string
  revision: string
  restoreUntil: string
  canRestore: boolean
}
export const renameAsset = (asset: Asset, name: string, key: string) =>
  request<Result<Asset>>({
    url: `/api/v1/assets/${asset.id}`,
    method: 'PATCH',
    data: { name, revision: asset.revision },
    headers: keyHeader(key),
  })
export const recycleAsset = (id: string, revision: string, restore: boolean, key: string) =>
  request<Result<Asset>>({
    url: `/api/v1/assets/${id}${restore ? '/restore' : ''}`,
    method: restore ? 'POST' : 'DELETE',
    ...(restore ? { data: { revision } } : { params: { revision } }),
    headers: keyHeader(key),
  })
export const listAssetTrash = (projectId: string, pageNum: number, signal: AbortSignal) =>
  request<{ code: number; rows: RecycledAsset[]; total: number }>({
    url: `/api/v1/projects/${projectId}/trash`,
    params: { kind: 'asset', pageNum, pageSize: 30 },
    signal,
  })
export interface LibraryEntry {
  createTime: string
  id: string
  name: string
  folderId: string | null
  revision: string
  asset: Asset
}
interface Result<T> {
  code: number
  data: T
}
export const moveLibraryEntry = (projectId: string, data: { entryId: string; folderId: string | null; revision: string }, key: string, signal: AbortSignal) =>
  request<Result<{ entryId: string; folderId: string | null; revision: string }>>({ url: `/api/v1/projects/${projectId}/library/move`, method: 'POST', data, headers: { 'Idempotency-Key': key }, signal })
export const copyLibraryEntry = (projectId: string, data: { entryId: string; folderId: string | null; revision: string }, key: string, signal: AbortSignal) =>
  request<Result<{ entryId: string; folderId: string | null; revision: string }>>({ url: `/api/v1/projects/${projectId}/library/copy`, method: 'POST', data, headers: { 'Idempotency-Key': key }, signal })
export const readAsset = (id: string, signal: AbortSignal) =>
  request<Result<Asset>>({ url: `/api/v1/assets/${id}`, signal })
export const outputToAsset = (
  id: string,
  data: { projectId: string; folderId: string | null; name: string },
  key: string,
  signal: AbortSignal,
) =>
  request<Result<Asset>>({
    url: `/api/v1/outputs/${id}/to-asset`,
    method: 'POST',
    data,
    signal,
    headers: { 'Idempotency-Key': key },
  })
const keyHeader = (key: string) => ({ 'Idempotency-Key': key })
export const createUpload = (
  projectId: string,
  file: File,
  sha256: string,
  key: string,
  signal: AbortSignal,
) =>
  request<Result<UploadSession>>({
    url: '/api/v1/uploads',
    method: 'POST',
    signal,
    data: {
      projectId,
      fileName: file.name,
      byteSize: String(file.size),
      mimeType: assetUploadMime(file) || file.type,
      sha256,
    },
    headers: keyHeader(key),
  })
export const readUpload = (id: string, signal: AbortSignal) =>
  request<Result<UploadSession>>({ url: `/api/v1/uploads/${id}`, signal })
export const putUploadPart = (
  id: string,
  part: number,
  data: Blob,
  start: number,
  total: number,
  sha: string,
  signal: AbortSignal,
  progress: (loaded: number) => void,
) =>
  request<Result<unknown>>({
    url: `/api/v1/uploads/${id}/parts/${part}`,
    method: 'PUT',
    data,
    signal,
    timeout: 120000,
    headers: {
      'Content-Type': 'application/octet-stream',
      'Content-Range': `bytes ${start}-${start + data.size - 1}/${total}`,
      'X-Content-SHA256': sha,
    },
    onUploadProgress: (event) => progress(event.loaded),
  })
export const completeUpload = (id: string, sha256: string, key: string, signal: AbortSignal) =>
  request<Result<UploadSession>>({
    url: `/api/v1/uploads/${id}/complete`,
    method: 'POST',
    data: { sha256 },
    headers: keyHeader(key),
    signal,
    timeout: 120000,
  })
export const bindAsset = (
  projectId: string,
  uploadId: string,
  name: string,
  folderId: string | null,
  key: string,
  signal: AbortSignal,
) =>
  request<Result<Asset>>({
    url: '/api/v1/assets',
    method: 'POST',
    data: { projectId, uploadId, name, folderId },
    headers: keyHeader(key),
    signal,
  })
export const bindAssetVersion = (assetId: string, revision: string, uploadId: string, key: string, signal: AbortSignal) =>
  request<Result<{ id: string; assetId: string; versionNo: number; fileId: string; revision: string }>>({
    url: `/api/v1/assets/${assetId}/versions`, method: 'POST', data: { revision, uploadId }, headers: keyHeader(key), signal,
  })
export const listAssets = (
  projectId: string,
  params: {
    folderId: string | null
    includeDescendants?: boolean
    q: string
    pageNum: number
    fileType?: AssetFileType
    from?: string
    to?: string
    activity?: 'generated' | 'uploaded' | 'liked' | 'downloaded'
  },
  signal: AbortSignal,
) =>
  request<{ code: number; rows: LibraryEntry[]; total: number }>({
    url: `/api/v1/projects/${projectId}/library`,
    params,
    signal,
  })
export const readMedia = (
  versionId: string,
  download: boolean,
  signal: AbortSignal,
  progress: (loaded: number) => void,
) =>
  requestBlob({
    url: `/api/v1/asset-versions/${versionId}/${download ? 'download' : 'preview'}`,
    signal,
    timeout: 120000,
    onDownloadProgress: (event) => progress(event.loaded),
  })

export const readThumbnail = (versionId: string, signal: AbortSignal) =>
  requestBlob({ url: `/api/v1/asset-versions/${versionId}/thumbnail`, signal })

export const readDocumentText = (versionId: string, signal: AbortSignal) =>
  request<Result<{ versionId: string; mimeType: string; sections: string[] }>>({
    url: `/api/v1/asset-versions/${versionId}/document-text`, signal,
  })

export const setAssetStatus = (asset: Asset, workStatus: AssetWorkStatus, key: string) =>
  request<Result<Asset>>({ url: `/api/v1/assets/${asset.id}/status`, method: 'PATCH',
    data: { revision: asset.revision, workStatus }, headers: keyHeader(key) })
