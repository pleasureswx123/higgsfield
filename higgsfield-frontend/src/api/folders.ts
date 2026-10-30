import { request } from './client'

export const readFolder = (id: string, signal?: AbortSignal) =>
  request<{ code: number; data: { folder: Folder; ancestors: Folder[] } }>({
    url: `/api/v1/folders/${encodeURIComponent(id)}`,
    signal,
  })

export type FolderKind = 'media' | 'element'
export type FolderColor = 'lime' | 'cyan' | 'slate' | 'violet' | 'purple' | 'pink' | 'yellow'
export type FolderSort = 'createdAsc' | 'createdDesc' | 'updatedDesc' | 'nameAsc' | 'nameDesc'
export interface Folder {
  id: string
  projectId: string
  parentId: string | null
  name: string
  description: string
  color: FolderColor
  folderKind: FolderKind
  orderNum: number
  revision: string
  hasChildren: boolean
}
export interface RecycleFolder {
  id: string
  targetId: string
  name: string
  revision: string
  deletedTime: string
  restoreUntil: string
  canRestore: boolean
}
export interface FolderPage<T> {
  code: number
  rows: T[]
  total: number
  hasNext: boolean
}
export interface FolderFields {
  name: string
  description: string
  color: FolderColor
}
export const listFolders = (
  projectId: string,
  params: {
    parentId?: string | null
    pageNum?: number
    pageSize?: number
    q?: string
    folderKind?: FolderKind
    sort?: FolderSort
  },
  signal?: AbortSignal,
) => request<FolderPage<Folder>>({ url: `/api/v1/projects/${projectId}/folders`, params, signal })
export const listFolderTrash = (projectId: string, pageNum = 1) =>
  request<FolderPage<RecycleFolder>>({
    url: `/api/v1/projects/${projectId}/trash`,
    params: { kind: 'folder', pageNum, pageSize: 30 },
  })
export const createFolder = (
  projectId: string,
  data: FolderFields & { parentId: string | null; folderKind: FolderKind },
  key: string,
) =>
  request<{ code: number; data: Folder }>({
    url: `/api/v1/projects/${projectId}/folders`,
    method: 'POST',
    data,
    headers: { 'Idempotency-Key': key },
  })
export const updateFolder = (id: string, data: FolderFields & { revision: string }, key: string) =>
  request<{ code: number; data: Folder }>({
    url: `/api/v1/folders/${id}`,
    method: 'PATCH',
    data,
    headers: { 'Idempotency-Key': key },
  })
export const actOnFolder = (
  id: string,
  action: 'move' | 'copy' | 'restore' | 'delete',
  data: {
    revision: string
    parentId?: string | null
    targetParentId?: string | null
    name?: string
  },
  key: string,
) =>
  request<{ code: number; data: Folder }>({
    url: `/api/v1/folders/${id}${action === 'delete' ? '' : '/' + action}`,
    method: action === 'delete' ? 'DELETE' : 'POST',
    ...(action === 'delete' ? { params: { ...data, mode: 'moveEntriesToParent' } } : { data }),
    headers: { 'Idempotency-Key': key },
  })

export interface FolderAssetCounts { total: number; folders: Record<string, number> }
export const readFolderAssetCounts = (projectId: string, signal?: AbortSignal) =>
  request<{ code: number; data: FolderAssetCounts }>({ url: `/api/v1/projects/${projectId}/folder-asset-counts`, signal })
