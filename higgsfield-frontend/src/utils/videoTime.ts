/** 将视频秒数格式化为时间标签，保留毫秒用于精确定位。 */
export function formatVideoTime(value: number | string, timecode = false): string {
  const ms = Math.max(0, Math.floor((Number(value) || 0) * 1000))
  const seconds = Math.floor(ms / 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  if (timecode) return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds / 60) % 60)}:${pad(seconds % 60)}:${String(ms % 1000).padStart(3, '0')}`
  return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`
}
