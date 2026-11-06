import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { useProjectActivityEvents } from './useProjectActivityEvents'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import { getGenerationActivity, type GenerationSummary } from '@/api/generations'
import { generationSubmissionFeedback } from '@/utils/generationFeedback'

/** 一个工作区共用 SSE 与授权快照，断线轮询兜底；不调用供应商。 */
export function useGenerationActivity(project: () => string, allowed: () => boolean) {
  const auth = useAuthStore()
  const count = ref<number>(), rows = ref<GenerationSummary[]>([])
  const error = ref(''), loading = ref(false), lastChecked = ref<number>()
  const autoUpdating = ref(false), epoch = ref(0)
  let inactive = false, disposed = false, failures = 0, again = false, accessRevoked = false
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let flight: Promise<void> | undefined
  const unseen = new Set<string>()
  let latestAccepted: string | undefined
  let missingAccepted = 0
  const visible = () => typeof document === 'undefined' || document.visibilityState !== 'hidden'
  const enabled = () => !inactive && !disposed && !accessRevoked && allowed() && !!auth.token && visible()
  const pending = (row: GenerationSummary) => (!['finished', 'blocked', 'submission_unknown'].includes(row.orchestrationState)
    && !['failed', 'cancelled'].includes(row.upstreamState)) || (row.orchestrationState !== 'submission_unknown' && row.archiveSummary.pending > 0)
  const events = useProjectActivityEvents(project, enabled, () => {
    clearTimeout(timer); void refresh()
  }, revoke, () => { if (enabled()) { clearTimeout(timer); void refresh() } })
  function revoke() {
    accessRevoked = true; stop()
    rows.value = []; count.value = undefined; latestAccepted = undefined; missingAccepted = 0; unseen.clear(); epoch.value++
    error.value = '当前任务状态不可访问，请检查登录或项目权限'
  }
  function stop() {
    events.stop()
    controller?.abort(); controller = undefined; flight = undefined; again = false
    clearTimeout(timer); autoUpdating.value = false; loading.value = false
  }
  function schedule() {
    if (!enabled()) return
    if (events.connected.value && !failures && !(latestAccepted && missingAccepted > 0 && missingAccepted < 3)) {
      autoUpdating.value = true
      return
    }
    const delay = failures ? Math.min(30000, 5000 * 2 ** (Math.min(failures, 4) - 1))
      : rows.value.some(row => pending(row) && generationSubmissionFeedback(row).busy) || (latestAccepted && !rows.value.some(row => row.id === latestAccepted) && missingAccepted < 3) ? 1000
      : count.value ? 5000 : 30000
    autoUpdating.value = true
    // 团队页面同时启动时错开后续查询，避免定时器集中冲击数据库。
    timer = setTimeout(() => { void refresh() }, delay + Math.floor(Math.random() * 500))
  }
  async function read(current: AbortController) {
    loading.value = true
    const identities = [...new Set([...unseen, ...(latestAccepted ? [latestAccepted] : []), ...rows.value.filter(pending).map(row => row.id)])]
    const next = new Map<string, GenerationSummary>()
    let page = 1, more = true, projectCount = 0
    try {
      while (more || (page - 1) * 100 < identities.length) {
        const result = await getGenerationActivity({ projectId: project(), pageNum: page,
          trackedIds: identities.slice((page - 1) * 100, page * 100).join(',') }, current.signal)
        if (current.signal.aborted) return
        for (const row of result.data.rows) next.set(row.id, row)
        projectCount = result.data.projectActiveCount
        more = result.data.hasNext; page++
      }
      // 仅保留本次授权响应；完成结果由展示层保存，撤权后不沿用旧任务。
      rows.value = [...next.values()]
      for (const id of next.keys()) unseen.delete(id)
      missingAccepted = latestAccepted && !next.has(latestAccepted) ? missingAccepted + 1 : 0
      count.value = projectCount; error.value = missingAccepted >= 3 ? '任务已受理，暂未查到状态，请刷新或查看生成记录' : ''; lastChecked.value = Date.now(); failures = 0
    } catch (cause) {
      if (current.signal.aborted) return
      failures++
      error.value = '状态暂未更新，显示上次结果；将自动重试'
      if (cause instanceof ApiError && (cause.code === 401 || cause.code === 403 || cause.errorCode === 'RESOURCE_NOT_FOUND')) {
        // 明确撤权必须立即清除旧内容；普通断网则保留最后成功状态。
        revoke()
      }
    } finally {
      if (controller === current) loading.value = false
    }
  }
  function refresh(): Promise<void> {
    if (!enabled()) return Promise.resolve()
    if (flight) { again = true; return flight }
    clearTimeout(timer); autoUpdating.value = false
    const current = new AbortController(); controller = current
    const request = read(current).finally(() => {
      if (controller !== current) return
      flight = undefined
      if (again) { again = false; void refresh() } else schedule()
    })
    flight = request
    return request
  }
  function track(id: string) { latestAccepted = id; unseen.add(id); missingAccepted = 0; void refresh() }
  watch(() => [project(), allowed(), auth.token, auth.user?.user.userId, JSON.stringify(auth.user?.permissions)], () => {
    stop(); accessRevoked = false; latestAccepted = undefined; missingAccepted = 0; unseen.clear(); rows.value = []; count.value = undefined
    error.value = ''; lastChecked.value = undefined; failures = 0; epoch.value++
    events.start(); void refresh()
  }, { immediate: true, flush: 'sync' })
  const resume = () => { if (visible()) { events.start(); void refresh() } else stop() }
  onMounted(() => { document.addEventListener('visibilitychange', resume); window.addEventListener('online', resume) })
  onDeactivated(() => { inactive = true; stop() })
  onActivated(() => { inactive = false; events.start(); if (!flight) void refresh() })
  onBeforeUnmount(() => {
    disposed = true; stop()
    document.removeEventListener('visibilitychange', resume); window.removeEventListener('online', resume)
  })
  return { count, rows, error, loading, lastChecked, autoUpdating, epoch, connected: events.connected, refresh: () => { accessRevoked = false; events.start(); return refresh() }, track }
}
export type GenerationActivityState = ReturnType<typeof useGenerationActivity>
