import type { GenerationOutput } from '@/api/generations'

export function archiveProgressText(progress?: GenerationOutput['archiveProgress']) {
  if (!progress?.stage) return ''
  if (progress.stage === 'failed') return '本次保存中断，正在记录重试状态…'
  if (progress.stage === 'verifying') return '下载完成，正在校验视频文件…'
  if (progress.stage === 'complete') return '文件校验完成，正在保存到素材库…'
  const size = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return progress.totalBytes
    ? `正在下载成片 ${size(progress.bytes ?? 0)} / ${size(progress.totalBytes)}`
    : `正在下载成片，已接收 ${size(progress.bytes ?? 0)}`
}
