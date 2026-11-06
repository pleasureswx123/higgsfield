import type { GenerationSummary } from '@/api/generations'

/** 展示真实执行阶段；等待超时仅提示延迟，不改写任务结果。 */
export function generationFeedback(row: GenerationSummary, now = Date.now()) {
  const state = row.orchestrationState
  const age = Math.max(0, now - Date.parse(row.createTime))
  const result = (label: string, description: string, busy = false, tone = 'neutral', spinning = false) => ({ label, description, busy, tone, spinning })
  if (state === 'submission_unknown') return row.requestState === 'transport_error'
    ? result('通信异常', '调用未取得有效响应，生成结果无法确认。可查看详情中的请求与异常记录，请勿重复提交。', true, 'warning')
    : result('异常', '提交结果尚未确认，请勿重复提交。', true, 'warning')
  if (row.upstreamState === 'failed' || state === 'blocked') return result('生成失败', '本次任务未完成，可查看记录中的具体原因。', false, 'danger')
  if (row.upstreamState === 'cancelled') return result('已取消', '任务已取消。')
  if (row.archiveSummary.failed) return result('保存异常', '部分结果未保存成功，已保存的结果仍可查看。', false, 'warning')
  if (row.archiveSummary.pending) return result('保存结果中', '生成结果正在保存到素材库，请勿重复提交。', true, 'progress', true)
  if (state === 'finished') return result(row.archiveSummary.ready ? '已完成' : '已结束', row.archiveSummary.ready ? `已保存 ${row.archiveSummary.ready} 个结果，可在素材列表中查看。` : '任务已结束，暂无可见结果。', false, row.archiveSummary.ready ? 'success' : 'neutral')
  if (state === 'accepted' && row.queueReason === 'capacity_unknown') return result('排队受阻', '生成服务有结果待核查的请求暂时占用名额，保护期结束后系统自动回收。本任务尚未发送，无需重复提交，可继续编辑其他创作。', false, 'warning')
  if (state === 'accepted' && row.queueReason === 'capacity_full') return result('等待生成名额', '生成服务当前名额已满，空出后会自动执行。本任务已保存，无需重复提交。', false, 'neutral')
  if (state === 'accepted') return age >= 120000
    ? result('请求尚未发出', '任务已保存，但尚未向生成服务发送请求，因此暂无生成结果。无需重复提交。', true, 'warning')
    : result('等待启动', '任务已保存，正在等待后台开始执行，尚未发送至生成服务。', true, 'progress', true)
  if (state === 'preparing') return result('准备素材中', '正在校验输入并准备参考素材，尚未开始生成。', true, 'progress', true)
  if (state === 'submitting') {
    if (row.requestState === 'response_received') return result('处理响应中', '已收到供应商响应，正在解析生成结果。', true, 'progress', true)
    if (row.requestState === 'transport_error') return result('通信异常', '本次调用未取得有效响应，正在确认结果，请勿重复提交。', true, 'warning')
    if (row.requestState === 'awaiting_response') return result('等待响应', '已发起生成请求，正在等待供应商响应，请勿重复提交。', true, 'progress', true)
    return result('正在提交', '正在向生成服务发送请求，请勿重复提交。', true, 'progress', true)
  }
  if (row.upstreamState === 'queued') return result('服务排队中', '生成服务已接收请求，正在等待处理。', true, 'progress', true)
  return result('生成中', '生成服务正在处理，完成后结果会自动保存到素材库。', true, 'progress', true)
}

/** 任务受理即结束提交；后台排队和生成由状态卡展示，不锁住创作入口。 */
export function generationSubmissionFeedback(row: GenerationSummary) {
  return { busy: false, label: '生成', spinning: false }
}
