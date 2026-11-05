import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { listGenerations } from '@/api/generations'

/** 只读取当前授权项目的进行中总数，不发起生成或重试。 */
export function useGenerationActivity(project: () => string, allowed: () => boolean) {
  const auth = useAuthStore()
  const count = ref(0)
  let inactive = false
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  function stop() { controller?.abort(); clearTimeout(timer) }
  async function refresh() {
    stop()
    if (inactive || !allowed() || !auth.token) { count.value = 0; return }
    const current = new AbortController()
    controller = current
    try {
      const result = await listGenerations({ scope: 'project', projectId: project(), category: 'active', pageNum: 1, pageSize: 1 }, current.signal)
      if (!current.signal.aborted) count.value = result.total
    } catch {
      if (!current.signal.aborted) count.value = 0
    } finally {
      if (!current.signal.aborted && !inactive) timer = setTimeout(() => { void refresh() }, count.value ? 5000 : 30000)
    }
  }
  watch(() => [project(), allowed(), auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions)], () => { count.value = 0; void refresh() }, { immediate: true, flush: 'sync' })
  onDeactivated(() => { inactive = true; stop(); count.value = 0 })
  onActivated(() => { inactive = false; void refresh() })
  onBeforeUnmount(() => { inactive = true; stop() })
  return { count, refresh }
}
