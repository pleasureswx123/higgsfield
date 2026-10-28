import type { MediaComment, Annotation } from '@/api/comments'

export interface CommentRecovery {
  key: string
  signature: string
  mode: 'thread' | 'save' | 'delete'
  row?: MediaComment
  threadId: string
  body: string
  videoTime?: string
  annotations?: Annotation[]
  annotationsChanged?: boolean
  parent?: MediaComment
  editing?: MediaComment
}

// 仅内存保存已发送意图，不进入浏览器持久存储；账号失效即清空。
let scope = ''
const pending = new Map<string, CommentRecovery>()
export function clearCommentRecovery() {
  scope = ''
  pending.clear()
}
export function readCommentRecovery(token: string, target: string) {
  if (scope !== token) {
    pending.clear()
    scope = token
  }
  const value = pending.get(target)
  return value ? structuredClone(value) : undefined
}
export function saveCommentRecovery(token: string, target: string, value: CommentRecovery) {
  if (scope === token) pending.set(target, JSON.parse(JSON.stringify(value)))
}
export function finishCommentRecovery(token: string, target: string, key: string) {
  if (scope === token && pending.get(target)?.key === key) pending.delete(target)
}
