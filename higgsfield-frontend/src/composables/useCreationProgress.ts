import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { listGenerations, type GenerationSummary } from '@/api/generations'
import { useAuthStore } from '@/stores/auth'

/** 从后端恢复目录生成状态；只查询任务，不重发供应商请求。 */
export function useCreationProgress(project: () => string, folder: () => string | null, accepted: () => string | undefined, changed: () => void) {
  const auth = useAuthStore()
  const rows = ref<GenerationSummary[]>([]), error = ref('')
  let active = true, disposed = false, controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let files = ''
  function stop() { controller?.abort(); if (timer) clearTimeout(timer) }
  async function reload() {
    stop()
    if (!active || disposed || !auth.token) { rows.value = []; return }
    const current = new AbortController()
    controller = current
    try {
      const result = await listGenerations({ scope: 'mine', projectId: project(), folderId: folder() || undefined, rootFolder: !folder(), pageNum: 1, pageSize: 10 }, current.signal)
      if (current.signal.aborted) return
      rows.value = result.rows
      error.value = ''
      const next = result.rows.map(row => `${row.id}:${row.archiveSummary.ready}`).join('|')
      if (next !== files) { files = next; changed() }
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '任务状态读取失败'
    } finally {
      if (!current.signal.aborted && active && !disposed) timer = setTimeout(() => { void reload() }, 5000)
    }
  }
  watch(() => [project(), folder(), accepted(), auth.token], () => { rows.value = []; files = ''; void reload() }, { immediate: true })
  onDeactivated(() => { active = false; stop() })
  onActivated(() => { active = true; void reload() })
  onBeforeUnmount(() => { disposed = true; stop() })
  function label(row: GenerationSummary) {
    const unit = row.kind === 'video' ? '个视频' : '张图片'
    if (row.orchestrationState === 'submission_unknown') return '结果待确认，请勿重复生成'
    if (row.upstreamState === 'failed' || row.orchestrationState === 'blocked') return '生成失败或被阻止，请查看详情'
    if (row.archiveSummary.failed) return `已保存 ${row.archiveSummary.ready} ${unit}，部分保存失败`
    if (row.orchestrationState === 'finished') return row.archiveSummary.ready ? `已保存 ${row.archiveSummary.ready} ${unit}` : '正在保存'
    return ['accepted', 'preparing'].includes(row.orchestrationState) ? '排队中' : '生成中'
  }
  return { rows, error, reload, label }
}
