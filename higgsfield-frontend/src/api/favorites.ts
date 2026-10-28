import { request } from './client'
export type FavoriteTarget = { elementId: string } | { assetId: string } | { outputId: string }
export type FavoriteKind = 'element' | 'asset' | 'output'
export interface Favorite {
  id: string
  target: FavoriteTarget
  kind: FavoriteKind
  createTime: string
  available: boolean
  source?: { name: string; projectId?: string; jobId?: string; mediaType?: string }
}
export const listFavorites = (pageNum: number, kind: FavoriteKind | '', signal: AbortSignal) =>
  request<{ code: number; rows: Favorite[]; total: number }>({
    url: '/api/v1/favorites',
    params: { pageNum, pageSize: 30, kind: kind || undefined },
    signal,
  })
export const saveFavorite = (target: FavoriteTarget, key: string, signal: AbortSignal) =>
  request<{ code: number; data: { id: string; target: FavoriteTarget } }>({
    url: '/api/v1/favorites',
    method: 'POST',
    data: { target },
    signal,
    headers: { 'Idempotency-Key': key },
  })
export const cancelFavorite = (id: string, key: string, signal: AbortSignal) =>
  request<{ code: number; data: { id: string; cancelled: boolean } }>({
    url: `/api/v1/favorites/${id}`,
    method: 'DELETE',
    signal,
    headers: { 'Idempotency-Key': key },
  })
