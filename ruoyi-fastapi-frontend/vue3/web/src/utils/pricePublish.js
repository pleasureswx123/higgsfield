import { toRfc3339 } from './time.js'
import { validRoutingId } from './routing.js'

export function priceEndPayload(form, activation) {
  if (!validRoutingId(activation?.id) || !validRoutingId(activation?.revision))
    throw new Error('区间ID或修订号无效，请刷新历史')
  const reason = form.reason.trim()
  if (!reason || reason.length > 4000) throw new Error('请填写结束原因，最多4000字符')
  if (!form.effectiveUntil) throw new Error('请选择结束时间')
  const effectiveUntil = toRfc3339(form.effectiveUntil, { timezoneName: 'Asia/Shanghai' })
  const end = Date.parse(effectiveUntil),
    start = Date.parse(activation.effectiveFrom)
  const previousEnd =
    activation.effectiveUntil === null ? Infinity : Date.parse(activation.effectiveUntil)
  if (!Number.isFinite(start) || Number.isNaN(previousEnd) || end <= start || end >= previousEnd)
    throw new Error('结束操作只能缩短区间，且须保留有效起点')
  return { revision: activation.revision, reason, effectiveUntil }
}

export function pricePublishPayload(form, revision) {
  if (!validRoutingId(revision)) throw new Error('价格版本号无效，请重新读取')
  const reason = form.reason.trim()
  if (!reason || reason.length > 4000) throw new Error('请填写发布原因，最多4000字符')
  if (!form.effectiveFrom) throw new Error('请选择生效起点')
  const effectiveFrom = toRfc3339(form.effectiveFrom, { timezoneName: 'Asia/Shanghai' })
  const effectiveUntil = form.effectiveUntil
    ? toRfc3339(form.effectiveUntil, { timezoneName: 'Asia/Shanghai' })
    : null
  if (effectiveUntil && Date.parse(effectiveUntil) <= Date.parse(effectiveFrom))
    throw new Error('结束时间必须晚于开始时间')
  const result = { revision, reason, effectiveFrom, effectiveUntil }
  if (form.replaceActivationId || form.expectedActivationRevision) {
    if (
      !validRoutingId(form.replaceActivationId) ||
      !validRoutingId(form.expectedActivationRevision)
    )
      throw new Error('替换区间ID与预期版本号必须同时填写有效值')
    result.replaceActivationId = form.replaceActivationId
    result.expectedActivationRevision = form.expectedActivationRevision
  }
  return result
}
