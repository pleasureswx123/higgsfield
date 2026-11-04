import { onActivated, onBeforeUnmount, onDeactivated, ref, watch, computed } from 'vue'
import { getGeneration, listGenerations, type GenerationSummary } from '@/api/generations'
import { useAuthStore } from '@/stores/auth'

/** 从后端恢复目录生成状态；只查询任务，不重发供应商请求。 */
export function useCreationProgress(project: () => string, folder: () => string | null, accepted: () => string | undefined, changed: () => void) {
  const auth = useAuthStore()
  const awaitingAccepted = ref(false)
  const rows = ref<GenerationSummary[]>([]), error = ref(''), loading = ref(false), lastChecked = ref<number>()
  const running = computed(() => rows.value.find(row => !['submission_unknown', 'blocked', 'finished'].includes(row.orchestrationState) && !['failed', 'cancelled'].includes(row.upstreamState)))
  const uncertain = computed(() => rows.value.find(row => row.orchestrationState === 'submission_unknown'))
  let active = true, disposed = false, controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  const autoUpdating = ref(false)
  let failures = 0
  let missingAccepted = 0
  let files = ''
  function stop() { controller?.abort(); if (timer) clearTimeout(timer); autoUpdating.value = false }
  function schedule() {
    if (!active || disposed) return
    autoUpdating.value = true
    timer = setTimeout(() => { void fetchState() }, 5000)
  }
  function failed(message: string) {
    error.value = message
    failures++
    if (failures < 3) schedule()
  }
  async function reload() { failures = 0; await fetchState() }
  async function fetchState() {
    stop()
    if (!active || disposed || !auth.token) { rows.value = []; return }
    const current = new AbortController()
    controller = current
    loading.value = true
    const deadline = setTimeout(() => {
      if (current.signal.aborted || !active || disposed || controller !== current) return
      current.abort()
      loading.value = false
      failed('状态查询超时')
    }, 15000)
    try {
      const result = await listGenerations({ scope: 'mine', projectId: project(), pageNum: 1, pageSize: 50 }, current.signal)
      if (current.signal.aborted) return
      let page = 1
      let more = result.hasNext
      while (more) {
        const older = await listGenerations({ scope: 'mine', projectId: project(), pageNum: ++page, pageSize: 50 }, current.signal)
        if (current.signal.aborted) return
        result.rows.push(...older.rows.filter(row => !['finished', 'blocked', 'submission_unknown'].includes(row.orchestrationState)))
        more = older.hasNext
      }
      for (const previous of rows.value.filter(row => !['finished', 'blocked', 'submission_unknown'].includes(row.orchestrationState))) {
        if (!result.rows.some(row => row.id === previous.id)) {
          const detail = await getGeneration(previous.id, current.signal)
          if (current.signal.aborted) return
          result.rows.push(detail.data)
        }
      }
      // 刚受理任务可能沿用参数记录的其他目录，必须按编号跟踪。
      const acceptedId = accepted()
      if (acceptedId && !result.rows.some(row => row.id === acceptedId)) {
        const detail = await getGeneration(acceptedId, current.signal)
        if (current.signal.aborted) return
        if (detail.data.projectId === project()) result.rows.unshift(detail.data)
      }
      rows.value = result.rows
      awaitingAccepted.value = Boolean(accepted() && !result.rows.some(row => row.id === accepted()))
      if (awaitingAccepted.value) missingAccepted++
      else missingAccepted = 0
      error.value = awaitingAccepted.value && missingAccepted >= 3 ? '任务已受理，暂未查到最新状态，请手动刷新' : ''
      failures = 0
      lastChecked.value = Date.now()
      const next = result.rows.filter(row => row.archiveSummary.ready > 0).map(row => `${row.id}:${row.archiveSummary.ready}`).join('|')
      if (next !== files) { files = next; changed() }
      // 人工核查和已结束的任务不再轮询；仍在处理或归档时才自动更新。
      if ((awaitingAccepted.value && missingAccepted < 3) || running.value || result.rows.some(row => row.orchestrationState !== 'submission_unknown' && row.archiveSummary.pending > 0)) schedule()
    } catch (cause) {
      if (!current.signal.aborted) failed(cause instanceof Error ? cause.message : '任务状态读取失败')
    } finally {
      clearTimeout(deadline)
      if (controller === current) loading.value = false
    }
  }
  watch(() => [project(), folder(), auth.token], () => { rows.value = []; files = ''; awaitingAccepted.value = false; lastChecked.value = undefined; void reload() }, { immediate: true })
  watch(accepted, value => { missingAccepted = 0; awaitingAccepted.value = Boolean(value); void reload() }, { flush: 'sync' })
  onDeactivated(() => { active = false; stop() })
  onActivated(() => { active = true; void reload() })
  onBeforeUnmount(() => { disposed = true; stop() })
  function label(row: GenerationSummary) {
    const unit = row.kind === 'video' ? '个视频' : '张图片'
    if (row.orchestrationState === 'submission_unknown') return '结果待确认，请勿重复生成'
    if (row.upstreamState === 'failed' || row.orchestrationState === 'blocked') return '生成失败或被阻止，请查看详情'
    if (row.upstreamState === 'cancelled') return '已取消'
    if (row.archiveSummary.failed) return `已保存 ${row.archiveSummary.ready} ${unit}，部分保存失败`
    if (row.orchestrationState === 'finished') return row.archiveSummary.ready ? `已保存 ${row.archiveSummary.ready} ${unit}` : row.archiveSummary.pending ? '正在保存结果' : '任务已结束，暂无可见结果'
    return ['accepted', 'preparing'].includes(row.orchestrationState) ? '排队中' : '生成中'
  }
  return { rows, error, autoUpdating, awaitingAccepted, loading, lastChecked, running, uncertain, reload, label }
}
