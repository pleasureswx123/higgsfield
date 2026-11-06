import { computed, ref, watch } from 'vue'
import type { GenerationSummary } from '@/api/generations'
import type { GenerationActivityState } from './useGenerationActivity'
import { ElNotification } from 'element-plus'
import { generationFeedback } from '@/utils/generationFeedback'

/** 共享工作区状态，只负责创作反馈和一次性通知，不另开轮询。 */
export function useCreationProgress(activity: GenerationActivityState, accepted: () => string | undefined,
  changed: (folders: (string | null)[]) => void, showResult: (id: string) => void = () => {}) {
  const rows = ref<GenerationSummary[]>([])
  const requestedAccepted = ref<string>()
  const observed = new Map<string, GenerationSummary>(), notified = new Set<string>(), submitted = new Set<string>()
  const readyCounts = new Map<string, number>()
  const running = computed(() => rows.value.find(row => !['submission_unknown', 'blocked', 'finished'].includes(row.orchestrationState) && !['failed', 'cancelled'].includes(row.upstreamState)))
  const uncertain = computed(() => rows.value.find(row => row.orchestrationState === 'submission_unknown'))
  const awaitingAccepted = computed(() => Boolean(requestedAccepted.value && !rows.value.some(row => row.id === requestedAccepted.value)))
  watch(activity.epoch, () => {
    requestedAccepted.value = undefined
    rows.value = []; observed.clear(); notified.clear(); submitted.clear(); readyCounts.clear()
  }, { flush: 'sync' })
  watch(activity.rows, nextRows => {
    const folders = new Set<string | null>()
    for (const row of nextRows) {
      const previous = observed.get(row.id)
      const feedback = generationFeedback(row)
      const ended = ['finished', 'blocked', 'submission_unknown'].includes(row.orchestrationState) || ['failed', 'cancelled'].includes(row.upstreamState) || row.archiveSummary.failed > 0
      const wasPending = previous && (!['finished', 'blocked', 'submission_unknown'].includes(previous.orchestrationState) || previous.archiveSummary.pending > 0)
      if (ended && !row.archiveSummary.pending && !notified.has(row.id) && (wasPending || submitted.has(row.id))) {
        notified.add(row.id)
        ElNotification({ title: feedback.label, message: `${row.promptExcerpt?.slice(0, 40) || (row.kind === 'video' ? '视频生成' : '图片生成')}：${feedback.description}`,
          type: feedback.tone === 'success' ? 'success' : feedback.tone === 'danger' ? 'error' : 'warning',
          onClick: () => showResult(row.id), duration: feedback.tone === 'success' ? 6000 : 0 })
      }
      if (row.archiveSummary.ready > (readyCounts.get(row.id) ?? 0)) folders.add(row.folderId ?? null)
      readyCounts.set(row.id, row.archiveSummary.ready); observed.set(row.id, row)
    }
    rows.value = nextRows
    // 清理已不再跟踪的展示缓存；授权响应没有返回的内容不继续展示。
    const ids = new Set(nextRows.map(row => row.id))
    for (const id of observed.keys()) if (!ids.has(id)) {
      observed.delete(id); readyCounts.delete(id); notified.delete(id); submitted.delete(id)
    }
    if (folders.size) changed([...folders])
  }, { immediate: true, flush: 'sync' })
  watch(accepted, id => { requestedAccepted.value = id; if (id) { submitted.add(id); activity.track(id) } }, { flush: 'sync', immediate: true })
  return { rows, running, uncertain, awaitingAccepted, error: activity.error, loading: activity.loading,
    lastChecked: activity.lastChecked, autoUpdating: activity.autoUpdating, reload: activity.refresh,
    label: (row: GenerationSummary) => generationFeedback(row).label }
}
