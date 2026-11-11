import { request } from './client'
import type { WorkStatus } from './elements'
export type ProductionKind = 'asset' | 'element'
export type ProductionAction =
  'reopen' | 'start' | 'submit' | 'withdraw' | 'request_changes' | 'approve'
export interface ProductionState {
  targetId: string
  kind: ProductionKind
  revision: string
  versionId: string
  workStatus: WorkStatus
  performerId: string | null
  performerName: string | null
  canAssign: boolean
  approvedVersionId: string | null
  reviewVerified: boolean
  allowedActions: ProductionAction[]
  history: {
    id: string
    action: string
    versionId: string | null
    actorId: string
    actorName: string
    fromStatus: WorkStatus
    toStatus: WorkStatus
    reason: string | null
    createTime: string
  }[]
}
export type ProductionCommand = {
  revision: string
  versionId: string
  action: ProductionAction
  reason?: string
}
const root = (kind: ProductionKind, id: string) =>
  '/api/v1/' + (kind === 'asset' ? 'assets' : 'elements') + '/' + id
export const readProduction = (kind: ProductionKind, id: string, signal: AbortSignal) =>
  request<{ code: number; data: ProductionState }>({ url: root(kind, id) + '/production', signal })
export const executeProduction = (
  kind: ProductionKind,
  id: string,
  data: ProductionCommand,
  key: string,
) =>
  request<{ code: number; data: ProductionState }>({
    url: root(kind, id) + '/production',
    method: 'POST',
    data,
    headers: { 'Idempotency-Key': key },
  })
export const assignProduction = (
  kind: ProductionKind,
  id: string,
  data: { revision: string; performerId: string | null },
  key: string,
) =>
  request<{ code: number; data: ProductionState }>({
    url: root(kind, id) + '/assignment',
    method: 'POST',
    data,
    headers: { 'Idempotency-Key': key },
  })
