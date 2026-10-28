import { request } from './client'
import type { ProjectStatus } from './projects'
import type { ElementCategory, WorkStatus } from './elements'
export interface ElementViewSettings {
  mineFilter?: 'all' | 'created' | 'favorites'
  cardSize: number
  splitByDate: boolean
  layout: 'grid' | 'board' | 'table'
  category: ElementCategory | null
  workStatus: WorkStatus | null
  statusGroup: 'active' | 'drafts' | null
}
export interface FolderViewSettings {
  expandedFolderIds?: string[]
  pinnedFolderIds?: string[]
  folderOrderIds?: string[]
}
export interface LibraryViewSettings extends FolderViewSettings {
  dates?: string[] | null
  includeDescendants?: boolean
  activity: 'generated' | 'uploaded' | 'liked' | 'downloaded' | null
  layout: 'square' | 'masonry'
  cardSize: number
  splitByDate: boolean
  fileType: 'image' | 'video' | 'pdf' | 'txt' | 'md' | 'html' | 'docx' | 'pptx' | null
}
export interface ProjectViewSettings {
  sort: 'created_desc' | 'created_asc' | 'name_asc'
  status: ProjectStatus | null
  hidden: boolean
  pinned: boolean
  collectionId: string | null
}
export interface ViewPreference<T> {
  viewKey: string
  projectId: string | null
  settings: T
  revision: string
}
export const getProjectViewPreference = (signal?: AbortSignal) =>
  request<{ code: number; data: ViewPreference<ProjectViewSettings> }>({
    url: '/api/v1/view-preferences/projects',
    signal,
  })
export const saveProjectViewPreference = (
  settings: ProjectViewSettings,
  revision: string,
  key: string,
  signal?: AbortSignal,
) =>
  request<{ code: number; data: ViewPreference<ProjectViewSettings> }>({
    url: '/api/v1/view-preferences/projects',
    method: 'PUT',
    data: { settings, revision },
    headers: { 'Idempotency-Key': key },
    signal,
  })
export const getElementViewPreference = (projectId: string | undefined, signal?: AbortSignal) =>
  request<{ code: number; data: ViewPreference<ElementViewSettings> }>({
    url: '/api/v1/view-preferences/elements',
    params: { projectId },
    signal,
  })
export const saveElementViewPreference = (
  projectId: string | undefined,
  settings: ElementViewSettings,
  revision: string,
  key: string,
  signal?: AbortSignal,
) =>
  request<{ code: number; data: ViewPreference<ElementViewSettings> }>({
    url: '/api/v1/view-preferences/elements',
    method: 'PUT',
    data: { projectId, settings, revision },
    headers: { 'Idempotency-Key': key },
    signal,
  })
export const getLibraryViewPreference = (projectId: string, signal?: AbortSignal) =>
  request<{ code: number; data: ViewPreference<LibraryViewSettings> }>({
    url: '/api/v1/view-preferences/library',
    params: { projectId },
    signal,
  })
export const saveLibraryViewPreference = (
  projectId: string,
  settings: LibraryViewSettings,
  revision: string,
  key: string,
  signal?: AbortSignal,
) =>
  request<{ code: number; data: ViewPreference<LibraryViewSettings> }>({
    url: '/api/v1/view-preferences/library',
    method: 'PUT',
    data: { projectId, settings, revision },
    headers: { 'Idempotency-Key': key },
    signal,
  })
