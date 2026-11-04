import { request } from './client'
import { recycleAsset } from './assets'
import { recycleElement } from './elements'
import { actOnFolder } from './folders'

export type TrashKind = 'asset' | 'element' | 'folder'
export interface TrashEntry {
  id: string
  targetId: string
  kind: TrashKind
  name: string
  revision: string
  deletedTime: string
  restoreUntil: string
  canRestore: boolean
}
export async function listProjectTrash(projectId: string, kind: TrashKind, pageNum: number, signal: AbortSignal) {
  const result = await request<{ code: number; rows: TrashEntry[]; total: number; hasNext: boolean }>({
    url: `/api/v1/projects/${projectId}/trash`, params: { kind, pageNum, pageSize: 30 }, signal,
  })
  return { ...result, rows: result.rows.map(row => ({ ...row, kind })) }
}
export function restoreProjectTrash(item: TrashEntry, key: string) {
  if (item.kind === 'asset') return recycleAsset(item.targetId, item.revision, true, key)
  if (item.kind === 'element') return recycleElement(item.targetId, item.revision, true, key)
  return actOnFolder(item.targetId, 'restore', { revision: item.revision }, key)
}
