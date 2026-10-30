import { ref, watch, onBeforeUnmount } from 'vue'
import { copyElement } from '@/api/elements'
import { searchReferences, type ReferenceCandidate } from '@/api/references'
import { useAuthStore } from '@/stores/auth'

/** 同一来源修订复用复制请求与结果，重试不重复创建元素。 */
export function usePickerElementCopy(projectId: () => string) {
  const auth = useAuthStore(), pending = ref(false), error = ref('')
  const intents = new Map<string, { key: string; alias: string; copiedId?: string }>()
  let epoch = 0
  function reset() { epoch++; intents.clear(); pending.value = false; error.value = '' }
  async function resolve(row: ReferenceCandidate): Promise<ReferenceCandidate | null> {
    if (pending.value || !auth.token) return null
    if (row.projectId === projectId()) return row
    const ticket = epoch, target = projectId(), identity = `${row.projectId}:${row.id}:${row.elementRevisionId}`
    let intent = intents.get(identity)
    if (!intent) {
      const key = crypto.randomUUID()
      intent = { key, alias: `${(row.alias || 'element').slice(0, 80)}_${key.slice(0, 8)}` }
      intents.set(identity, intent)
    }
    pending.value = true; error.value = ''
    try {
      if (!intent.copiedId) {
        const result = await copyElement(row.id, { targetProjectId: target, sourceRevisionId: row.elementRevisionId!, name: row.displayName, alias: intent.alias }, intent.key)
        if (ticket !== epoch) return null
        intent.copiedId = result.data.id
      }
      const result = await searchReferences({ projectId: target, kind: 'element', elementId: intent.copiedId, q: '', pageNum: 1, pageSize: 1 })
      if (ticket !== epoch) return null
      const candidate = result.rows[0]
      if (!candidate) throw new Error('已复制到当前项目，但暂无可引用图片或引用权限')
      return candidate
    } catch (cause) {
      if (ticket === epoch) error.value = cause instanceof Error ? cause.message : '复制元素失败，请重试'
      return null
    } finally { if (ticket === epoch) pending.value = false }
  }
  watch(() => [projectId(), auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions || [])], reset, { flush: 'sync' })
  onBeforeUnmount(reset)
  return { pending, error, resolve }
}
