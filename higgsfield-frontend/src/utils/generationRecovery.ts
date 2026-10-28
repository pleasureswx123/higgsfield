import type { GenerationSubmission } from '@/api/generations'

export interface GenerationRecovery { data: GenerationSubmission; key: string }
// 仅保留当前登录会话的待确认请求，不将提示词、引用或令牌写入持久存储。
let scope = ''
const pending = new Map<string, GenerationRecovery>()
export function clearGenerationRecovery() { scope = ''; pending.clear() }
export function readGenerationRecovery(token: string, projectId: string) {
  if (scope !== token) { pending.clear(); scope = token }
  const value = pending.get(projectId)
  return value ? structuredClone(value) : undefined
}
export function saveGenerationRecovery(token: string, projectId: string, value: GenerationRecovery) {
  if (scope === token && !pending.has(projectId)) pending.set(projectId, structuredClone(value))
}
export function finishGenerationRecovery(token: string, projectId: string, key: string) {
  if (scope === token && pending.get(projectId)?.key === key) pending.delete(projectId)
}
