import { request } from './client'
export type CommentTarget = { assetVersionId: string } | { outputId: string }
export interface Annotation {
  shape: 'point' | 'rect' | 'path'
  geometry: Record<string, unknown>
  color: string
  sourceWidth: number
  sourceHeight: number
}
export interface CommentThread {
  id: string
  target: CommentTarget
  revision: string
  resolvedAt: string | null
  createTime: string
}
export interface MediaComment {
  id: string
  threadId: string
  parentId: string | null
  body: string
  revision: string
  deleted: boolean
  author: { id: string; displayName: string } | null
  createTime: string
  videoTime?: string | null
  annotations: Annotation[]
  reactions?: { emoji: string; userId: string }[]
  allowedActions?: string[]
}
export interface CommentInput {
  body: string
  parentId?: string
  videoTime?: string
  annotations?: Annotation[]
}
export const listCommentThreads = (target: CommentTarget, pageNum: number, signal: AbortSignal) =>
  request<{ code: number; rows: CommentThread[]; total: number }>({
    url: '/api/v1/comment-threads',
    params: { ...target, pageNum, pageSize: 10 },
    signal,
  })
export const createCommentThread = (target: CommentTarget, key: string, signal: AbortSignal) =>
  request<{ code: number; data: CommentThread }>({
    url: '/api/v1/comment-threads',
    method: 'POST',
    data: { target },
    signal,
    headers: { 'Idempotency-Key': key },
  })
export const listComments = (id: string, pageNum: number, signal: AbortSignal) =>
  request<{ code: number; rows: MediaComment[]; total: number }>({
    url: `/api/v1/comment-threads/${id}/comments`,
    params: { pageNum, pageSize: 30 },
    signal,
  })
export const postComment = (id: string, data: CommentInput, key: string, signal: AbortSignal) =>
  request<{ code: number; data: MediaComment }>({
    url: `/api/v1/comment-threads/${id}/comments`,
    method: 'POST',
    data,
    signal,
    headers: { 'Idempotency-Key': key },
  })
export const changeComment = (
  id: string,
  data: { revision: string; body?: string; annotations?: Annotation[] },
  remove: boolean,
  key: string,
  signal: AbortSignal,
) =>
  request<{ code: number; data: MediaComment }>({
    url: `/api/v1/comments/${id}`,
    method: remove ? 'DELETE' : 'PATCH',
    ...(remove ? { params: { revision: data.revision } } : { data }),
    signal,
    headers: { 'Idempotency-Key': key },
  })

export const updateCommentThread = (id:string, data:{revision:string;action:'resolve'|'reopen'|'delete'}, key:string, signal:AbortSignal) => request<{code:number;data:CommentThread}>({url:`/api/v1/comment-threads/${id}`,method:'PATCH',data,signal,headers:{'Idempotency-Key':key}})
export const setCommentReaction = (id:string,data:{emoji:string;active:boolean},key:string,signal:AbortSignal) => request<{code:number;data:MediaComment}>({url:`/api/v1/comments/${id}/reaction`,method:'PATCH',data,signal,headers:{'Idempotency-Key':key}})
