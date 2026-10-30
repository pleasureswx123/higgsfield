import { request } from './client'
export type PermissionScope = 'none' | 'own' | 'project'
export interface PermissionRow { group: string; code: string; label: string; scoped: boolean; editable: boolean }
export interface PermissionRole { code: string; name: string; defaults: Record<string, PermissionScope>; permissions: Record<string, PermissionScope> }
export interface PermissionMatrix { revision: string; canEdit: boolean; rows: PermissionRow[]; roles: PermissionRole[] }
export const readProjectPermissions = (id: string, signal?: AbortSignal) => request<{ code: number; data: PermissionMatrix }>({ url: `/api/v1/projects/${encodeURIComponent(id)}/role-permissions`, signal })
export const saveProjectPermissions = (id: string, data: { revision: string; overrides: Record<string, Record<string, PermissionScope>> }, key: string) => request<{ code: number; data: PermissionMatrix }>({ url: `/api/v1/projects/${encodeURIComponent(id)}/role-permissions`, method: 'PUT', data, headers: { 'Idempotency-Key': key } })
