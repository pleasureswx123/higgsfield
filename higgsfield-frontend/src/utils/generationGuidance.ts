import type { GenerationSnapshot } from '@/api/generations'

export interface GenerationGuidance {
  code: string
  title: string
  message: string
}

/** 仅解释已确认的状态，不从网络错误推断供应商是否受理或收费。 */
export function generationGuidance(task: GenerationSnapshot): GenerationGuidance[] {
  const items: GenerationGuidance[] = []
  if (task.orchestrationState === 'submission_unknown' || task.upstreamState === 'unknown') {
    items.push({ code: 'unknown', title: '提交结果待核查',
      message: '目前无法确认供应商是否已受理或完成。请保留任务编号并联系管理员核查；刷新只查询当前任务。不要重复生成来试探结果，以免产生另一笔费用。' })
  } else if (task.upstreamState === 'failed') {
    items.push({ code: 'failed', title: '生成失败',
      message: `${task.diagnostic ? '请结合下方已记录的原因联系管理员核查。' : '已记录上游失败状态，当前详情未提供可核实的具体失败原因。请携任务编号联系管理员查看脱敏证据。'}失败不等于免费；复制输入只保存新草稿，再次提交是独立任务并可能产生新费用。` })
  } else if (task.cancelState === 'confirmed' || task.upstreamState === 'cancelled') {
    items.push({ code: 'cancelled', title: '任务已取消',
      message: '取消状态与费用状态分别记录。是否释放预算、是否已产生费用，以核实后的费用记录为准，不将取消自动视为免费。' })
  } else if (task.orchestrationState === 'blocked') {
    items.push({ code: 'blocked', title: '任务处理受阻',
      message: '当前任务需要核查，请提供任务编号给管理员。此状态不证明供应商未受理；不要通过重复提交绕过处理。' })
  } else if (task.orchestrationState === 'accepted' || task.orchestrationState === 'preparing') {
    items.push({ code: 'preparing', title: '后台准备中',
      message: '关闭页面不会取消任务。只有页面提供取消入口时才能申请取消；实际是否取消成功以服务端返回状态为准。' })
  } else if (task.orchestrationState === 'running' || task.orchestrationState === 'submitting') {
    items.push({ code: 'running', title: '后台处理中',
      message: '任务由服务端继续处理，关闭页面或隐藏任务不会停止供应商消费。可稍后重新打开查看结果，刷新不会重新生成。' })
  }
  if (task.outputsVisibility === 'visible' && task.outputs.some(output => output.archiveState === 'source_expired')) {
    items.push({ code: 'expired', title: '部分结果链接已过期',
      message: '请联系管理员核查原任务结果是否可以恢复。重新生成会创建新任务，不能当作本次归档恢复，也不能覆盖原费用记录。' })
  }
  if (task.archiveSummary?.failed > 0) {
    items.push({ code: 'archive_failed', title: '部分结果尚未归档成功',
      message: '有归档权限且源仍可用的输出可单独重试归档；该操作不重新提交模型生成。已就绪的其他输出仍可按权限使用，费用不按下载成功数量折算。' })
  } else if (task.upstreamState === 'succeeded' && task.archiveSummary?.pending > 0) {
    items.push({ code: 'archiving', title: '生成成功，归档尚未完成',
      message: '生成成功与长期归档是两个独立状态。请等待各输出归档就绪后再使用公司长期文件；无需再次生成。' })
  }
  return items
}
