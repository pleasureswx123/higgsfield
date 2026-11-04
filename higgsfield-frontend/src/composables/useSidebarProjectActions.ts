import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getProjectPreference, putProjectPreference } from '@/api/projectPreferences'
import { readBrief } from '@/api/projectWorkspace'
import { ApiError } from '@/api/client'
import type { Project } from '@/api/projects'
import { useAuthStore } from '@/stores/auth'
import { useProjectUpdatesStore } from '@/stores/projectUpdates'

export function useSidebarProjectActions(project: () => Project) {
  const auth = useAuthStore(), updates = useProjectUpdatesStore()
  const busy = ref(false), checking = ref(false), error = ref(''), canEdit = ref(false)
  const retry = ref(false)
  let reader: AbortController | undefined, writer: AbortController | undefined
  let intent: { id: string; key: string; data: { revision: string; isPinned?: boolean; isHidden?: boolean } } | undefined
  const hidden = computed(() => Boolean(project().preference?.isHidden))
  const pinned = computed(() => Boolean(project().preference?.isPinned))
  async function inspect(open: boolean) {
    if (!open) return
    reader?.abort(); reader = new AbortController()
    const signal = reader.signal
    checking.value = true; canEdit.value = false
    try {
      const result = await readBrief(project().id, signal)
      if (!signal.aborted) canEdit.value = result.data.allowedActions.includes('project:manage') && project().status === 'active'
    } catch (cause) {
      if (!signal.aborted) error.value = cause instanceof Error ? cause.message : '权限读取失败'
    } finally { if (!signal.aborted) checking.value = false }
  }
  async function togglePreference(field: 'isPinned' | 'isHidden') {
    if (busy.value) return
    busy.value = true; error.value = ''
    writer = new AbortController()
    const signal = writer.signal
    try {
      if (!intent) {
        const id = project().id
        const result = await getProjectPreference(id, signal)
        if (signal.aborted) return
        intent = { id, key: crypto.randomUUID(), data: { revision: result.data.revision, [field]: !result.data[field] } }
      }
      retry.value = true
      await putProjectPreference(intent.id, intent.data, intent.key, signal)
      if (signal.aborted) return
      intent = undefined; retry.value = false; updates.notify()
    } catch (cause) {
      if (signal.aborted) return
      if (cause instanceof ApiError && ((cause.code === 601 && cause.errorCode !== 'IDEMPOTENCY_IN_PROGRESS') || (cause.code >= 400 && cause.code < 500))) {
        intent = undefined; retry.value = false
      }
      error.value = cause instanceof Error ? cause.message : '项目操作失败，请重试'
    } finally { if (!signal.aborted) busy.value = false }
  }
  function clear() {
    reader?.abort(); writer?.abort(); intent = undefined
    busy.value = false; checking.value = false; retry.value = false; error.value = ''; canEdit.value = false
  }
  watch(() => [auth.token, auth.user?.user.userId], clear)
  onBeforeUnmount(clear)
  return { busy, checking, error, canEdit, retry, pinned, inspect, hidden, togglePin: () => togglePreference('isPinned'), toggleHidden: () => togglePreference('isHidden') }
}
