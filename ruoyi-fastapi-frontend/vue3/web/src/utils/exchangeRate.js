import { toRfc3339 } from './time.js'
import { validRoutingId } from './routing.js'

export function exchangeRatePayload(form) {
  if (
    ![form.baseCurrency, form.quoteCurrency].every((value) => /^[A-Z]{3}$/.test(value)) ||
    form.baseCurrency === form.quoteCurrency
  )
    throw new Error('请选择不同的三位大写币种')
  if (
    typeof form.rate !== 'string' ||
    !/^(0|[1-9]\d{0,11})(\.\d{1,12})?$/.test(form.rate) ||
    !/[1-9]/.test(form.rate)
  )
    throw new Error('汇率须大于零，最多12位整数和12位小数')
  if (!validRoutingId(form.sourceId)) throw new Error('请输入有效来源证据ID')
  if (!form.validFrom) throw new Error('请选择生效起点')
  const validFrom = toRfc3339(form.validFrom, { timezoneName: 'Asia/Shanghai' })
  const validUntil = form.validUntil
    ? toRfc3339(form.validUntil, { timezoneName: 'Asia/Shanghai' })
    : null
  if (validUntil && Date.parse(validUntil) <= Date.parse(validFrom))
    throw new Error('结束时间必须晚于开始时间')
  return {
    baseCurrency: form.baseCurrency,
    quoteCurrency: form.quoteCurrency,
    rate: form.rate,
    sourceId: form.sourceId,
    validFrom,
    validUntil,
  }
}

export function exchangeRatePublishPayload(revision, reason) {
  if (!validRoutingId(revision)) throw new Error('修订号无效，请刷新列表')
  if (!reason.trim() || reason.trim().length > 4000) throw new Error('请填写发布原因，最多4000字符')
  return { revision, reason: reason.trim() }
}
