import { toRfc3339 } from './time.js'

export function priceSourcePayload(form, now = Date.now()) {
  if (!['vendor_document', 'official_screenshot', 'manual_confirmation'].includes(form.sourceType))
    throw new Error('请选择有效的来源类型')
  const sourceUrl = form.sourceUrl.trim() || null
  if (sourceUrl) {
    let url
    try {
      url = new URL(sourceUrl)
    } catch {
      throw new Error('出处地址无效')
    }
    if (
      sourceUrl.length > 4000 ||
      !['https:', 'http:'].includes(url.protocol) ||
      !url.hostname ||
      url.username ||
      url.password ||
      /[\u0000-\u0020]/.test(sourceUrl)
    )
      throw new Error('出处必须为不含凭据和空白的HTTP/HTTPS地址')
  }
  const uploadId = form.uploadId || undefined
  if (uploadId && !/^[1-9][0-9]*$/.test(uploadId)) throw new Error('附件上传标识无效')
  if (form.sourceType !== 'manual_confirmation' && !sourceUrl && !uploadId)
    throw new Error('文档或截图来源必须提供出处地址或已校验附件')
  const excerpt = form.excerpt.trim()
  if (!excerpt || excerpt.length > 20000) throw new Error('来源摘录不能为空，最多20000字符')
  if (!form.observedAt) throw new Error('请选择获取时间')
  const observedAt = toRfc3339(form.observedAt, { timezoneName: 'Asia/Shanghai' })
  if (!Number.isFinite(Date.parse(observedAt)) || Date.parse(observedAt) > now)
    throw new Error('来源获取时间不能晚于当前时间')
  return { sourceType: form.sourceType, sourceUrl, excerpt, observedAt, ...(uploadId ? { uploadId } : {}) }
}
