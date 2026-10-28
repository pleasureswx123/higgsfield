/** 按能力定义解析单一维度，不把布尔值或字符串隐式转换成数字。 */
export function parseVariantDimension(rule, input) {
  let value
  if (rule.enum != null) {
    const index = rule.enum.findIndex((item) => JSON.stringify(item) === input)
    if (index < 0) throw new Error('请选择允许的规格值')
    value = rule.enum[index]
  } else if (rule.type === 'string') value = input
  else if (rule.type === 'boolean') {
    if (!['true', 'false'].includes(input)) throw new Error('请选择是或否')
    value = input === 'true'
  } else {
    if (typeof input !== 'string' || !/^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$/.test(input))
      throw new Error('请输入有效数字')
    value = Number(input)
  }
  if (rule.type === 'integer' && !Number.isSafeInteger(value))
    throw new Error('整数必须在浏览器可精确表示的范围内')
  if (['integer', 'number'].includes(rule.type)) {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('请输入有限数字')
    if (Number.isInteger(value) && !Number.isSafeInteger(value))
      throw new Error('数字超出浏览器可精确表示范围')
    if (rule.minimum != null && value < rule.minimum) throw new Error(`不得小于 ${rule.minimum}`)
    if (rule.maximum != null && value > rule.maximum) throw new Error(`不得大于 ${rule.maximum}`)
  } else if (rule.type === 'string') {
    if (typeof value !== 'string') throw new Error('请输入字符串')
    const length = Array.from(value).length
    if (rule.minLength != null && length < rule.minLength)
      throw new Error(`至少 ${rule.minLength} 个字符`)
    if (rule.maxLength != null && length > rule.maxLength)
      throw new Error(`最多 ${rule.maxLength} 个字符`)
  } else if (rule.type !== 'boolean' || typeof value !== 'boolean') throw new Error('规格类型无效')
  return value
}

export function variantPayload(rules, inputs) {
  return {
    dimensions: Object.fromEntries(
      Object.entries(rules).map(([key, rule]) => [key, parseVariantDimension(rule, inputs[key])])
    ),
  }
}
