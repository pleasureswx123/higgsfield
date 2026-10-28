export interface OutputAssetRecovery {
  key: string
  data: { projectId: string; folderId: string | null; name: string }
}

// 仅在本次登录的内存中保留已发送请求，不保存到浏览器持久存储。
let scope = ''
const pending = new Map<string, OutputAssetRecovery>()
export function clearOutputAssetRecovery() { scope = ''; pending.clear() }
export function readOutputAssetRecovery(token: string, outputId: string) {
  if (scope !== token) { pending.clear(); scope = token }
  const value = pending.get(outputId)
  return value ? structuredClone(value) : undefined
}
export function saveOutputAssetRecovery(token: string, outputId: string, value: OutputAssetRecovery) {
  if (scope === token) pending.set(outputId, structuredClone(value))
}
export function finishOutputAssetRecovery(token: string, outputId: string, key: string) {
  if (scope === token && pending.get(outputId)?.key === key) pending.delete(outputId)
}
