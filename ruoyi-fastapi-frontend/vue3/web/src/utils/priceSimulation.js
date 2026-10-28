import { validRoutingId } from './routing'

export const simulationFields = [
  ['inputTokens', '输入Token'],
  ['outputTokens', '输出Token'],
  ['videoTokens', '视频Token'],
  ['characters', '字符数'],
  ['imageCount', '图片张数'],
  ['outputSeconds', '输出秒数'],
  ['referenceSeconds', '参考秒数'],
]

export function priceSimulationPayload(form) {
  let dimensions
  try {
    dimensions = JSON.parse(form.dimensions)
  } catch {
    throw new Error('规格维度必须为合法JSON对象')
  }
  if (
    !dimensions ||
    Array.isArray(dimensions) ||
    typeof dimensions !== 'object' ||
    Object.keys(dimensions).length > 100
  )
    throw new Error('规格维度必须为对象，最多100个维度')
  for (const [name, value] of Object.entries(dimensions)) {
    if (
      !name ||
      name.length > 100 ||
      !['string', 'boolean', 'number'].includes(typeof value) ||
      (typeof value === 'string' && value.length > 1000) ||
      (typeof value === 'number' &&
        (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))))
    )
      throw new Error('规格维度值须为字符串、布尔或可精确表示的有限数字')
  }
  const usage = {}
  for (const [name, label] of simulationFields) {
    const value = form[name]
    if (value === '') continue
    if (typeof value !== 'string') throw new Error(`${label}格式错误`)
    if (name.endsWith('Seconds')) {
      if (!/^(0|[1-9]\d{0,17})(\.\d{1,6})?$/.test(value))
        throw new Error(`${label}最多18位整数、6位小数`)
      usage[name] = value
    } else {
      if (
        !/^(0|[1-9]\d{0,18})$/.test(value) ||
        BigInt(value) > (name === 'imageCount' ? 2147483647n : 9223372036854775807n)
      )
        throw new Error(`${label}须为范围内的非负整数`)
      usage[name] = name === 'imageCount' ? Number(value) : value
    }
  }
  const result = { dimensions, usage }
  if (form.exchangeRateVersionId) {
    if (!validRoutingId(form.exchangeRateVersionId)) throw new Error('汇率版本ID无效')
    result.exchangeRateVersionId = form.exchangeRateVersionId
  }
  return result
}
