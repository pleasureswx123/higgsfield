/** 保留服务端十进制精度，仅去除无意义尾零，不转换为浮点数。 */
export function formatBillingDecimal(value: string | null | undefined): string {
  if (value == null || !/^(0|[1-9]\d*)(\.\d+)?$/.test(value)) return '待确认'
  if (!value.includes('.')) return value
  return value.replace(/0+$/, '').replace(/\.$/, '')
}

/** 预算可用额允许为负，不能以零掩盖实际超额。 */
export function formatBudgetDecimal(value: string): string {
  if (value.startsWith('-')) {
    const magnitude = formatBillingDecimal(value.slice(1))
    return magnitude === '待确认' ? magnitude : magnitude === '0' ? '0' : `-${magnitude}`
  }
  return formatBillingDecimal(value)
}
