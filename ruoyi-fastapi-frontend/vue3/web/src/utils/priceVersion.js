import { validRoutingId } from './routing'

// 使用十进制整数缩放比较，避免金额和阶梯数量经过浮点转换。
function decimal(value, digits, scale) {
  if (
    typeof value !== 'string' ||
    !new RegExp(`^(0|[1-9][0-9]{0,${digits - 1}})(\\.[0-9]{1,${scale}})?$`).test(value)
  )
    throw new Error('金额或数量格式、精度超出允许范围')
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole + fraction.padEnd(scale, '0'))
}

export function priceVersionPayload(form) {
  if (
    !Number.isInteger(form.calculationScale) ||
    form.calculationScale < 0 ||
    form.calculationScale > 10
  )
    throw new Error('计算小数位须为0至10的整数')
  const sourceIds = form.sourceIds.trim() ? form.sourceIds.trim().split(/[\s,，]+/) : []
  if (
    sourceIds.length > 100 ||
    sourceIds.some((id) => !validRoutingId(id)) ||
    new Set(sourceIds).size !== sourceIds.length
  )
    throw new Error('来源ID须为不重复的有效ID，最多100个')
  if (!Array.isArray(form.items) || form.items.length > 1000)
    throw new Error('最多配置1000个计价分项')
  const starts = new Set()
  const items = form.items.map((item) => {
    if (!/^[a-z][a-z0-9_]{0,99}$/.test(item.itemCode))
      throw new Error('计价分项编码须为小写字母开头的字母、数字或下划线')
    if (
      !['token', 'image', 'second', 'character'].includes(item.unit) ||
      !['linear', 'tiered'].includes(item.formulaTemplate)
    )
      throw new Error('请选择有效的计价单位与公式')
    if (decimal(item.unitQuantity, 12, 6) <= 0n) throw new Error('单价基数必须大于零')
    const price = decimal(item.unitPrice, 14, 10),
      from = decimal(item.quantityFrom, 18, 6)
    const quantityTo = item.quantityTo === '' || item.quantityTo == null ? null : item.quantityTo
    if (quantityTo !== null && decimal(quantityTo, 18, 6) <= from)
      throw new Error('阶梯上限必须大于下限')
    const identity = `${item.itemCode}:${from}`
    if (starts.has(identity)) throw new Error('同一分项不能重复登记相同阶梯起点')
    starts.add(identity)
    const freeReason = (item.freeReason || '').trim() || null
    if ((price === 0n && !freeReason) || (freeReason && freeReason.length > 4000))
      throw new Error('零价必须提供免费依据，依据最多4000字符')
    return {
      itemCode: item.itemCode,
      unit: item.unit,
      unitQuantity: item.unitQuantity,
      unitPrice: item.unitPrice,
      quantityFrom: item.quantityFrom,
      quantityTo,
      formulaTemplate: item.formulaTemplate,
      freeReason,
    }
  })
  return { roundingMode: 'half_up', calculationScale: form.calculationScale, items, sourceIds }
}

export function emptyPriceItem() {
  return {
    itemCode: '',
    unit: 'image',
    unitQuantity: '1',
    unitPrice: '',
    quantityFrom: '0',
    quantityTo: '',
    formulaTemplate: 'linear',
    freeReason: '',
  }
}
