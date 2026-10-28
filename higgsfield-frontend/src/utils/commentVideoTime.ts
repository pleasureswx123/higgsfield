// 与后端numeric(18,6)保持一致；正文请求不经浮点转换。
export function validCommentVideoTime(value: string) {
  return /^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/.test(value)
}
export function playerTimeToComment(value: number) {
  if (!Number.isFinite(value) || value < 0 || value >= 1e12) return ''
  const formatted = value.toFixed(6).replace(/\.?0+$/, '')
  return validCommentVideoTime(formatted) ? formatted : ''
}
