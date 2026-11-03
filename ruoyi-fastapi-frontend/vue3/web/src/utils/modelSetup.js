/** 接入助手只补齐当前模型配置，不替换其他模型或其他供应商的路由。 */
export function appendSetupRoute(current, modelId, accountId, credentialId) {
  const routes = structuredClone(current.routes)
  const existing = routes.find(row => row.modelId === modelId && row.accountId === accountId)
  if (existing) {
    existing.enabled = true
    if (!existing.credentials.some(row => row.credentialId === credentialId)) {
      existing.credentials.push({ credentialId, priority: 100, maxConcurrency: 1 })
    }
  } else {
    routes.push({ modelId, accountId, priority: 100, enabled: true,
      credentials: [{ credentialId, priority: 100, maxConcurrency: 1 }] })
  }
  return { revision: current.revision, routes }
}

export function setupPriceItems(input, output) {
  const valid = value => /^(0|[1-9]\d{0,13})(\.\d{1,10})?$/.test(value) && Number(value) > 0
  if (!valid(input) || !valid(output)) throw new Error('请输入大于零的美元单价，最多保留 10 位小数')
  return [['input', input], ['output', output]].map(([itemCode, unitPrice]) => ({
    itemCode, unit: 'token', unitQuantity: '1000000', unitPrice,
    formulaTemplate: 'linear', quantityFrom: '0', quantityTo: null, freeReason: null,
  }))
}

export function sameSetupPrice(version, items) {
  const decimal = value => String(value).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
  return version.items?.length === items.length && items.every(expected => version.items.some(actual =>
    actual.itemCode === expected.itemCode && actual.unit === expected.unit && actual.formulaTemplate === expected.formulaTemplate
    && decimal(actual.unitQuantity) === decimal(expected.unitQuantity) && decimal(actual.unitPrice) === decimal(expected.unitPrice)
    && decimal(actual.quantityFrom) === decimal(expected.quantityFrom)
    && (expected.quantityTo == null ? actual.quantityTo == null : decimal(actual.quantityTo) === decimal(expected.quantityTo))))
}

/** 历史事件可能多次修改同一区间，只取每个区间最新事实。 */
export function activeSetupActivation(history, now = Date.now()) {
  const seen = new Set()
  for (const event of history) {
    const activation = event.diff?.after
    if (!activation?.id || seen.has(activation.id)) continue
    seen.add(activation.id)
    if (Date.parse(activation.effectiveFrom) <= now &&
        (!activation.effectiveUntil || Date.parse(activation.effectiveUntil) > now)) return activation
  }
  return null
}

export const activeSetupPrice = (history, now) => Boolean(activeSetupActivation(history, now))

/** 读取所有分页，避免把第一页之外的已配数据误判为不存在。 */
export async function setupRows(loader, params = {}) {
  const rows = []
  for (let pageNum = 1; pageNum <= 1000; pageNum++) {
    const result = await loader({ ...params, pageNum, pageSize: 100 })
    rows.push(...(result.rows || []))
    if (result.hasNext === false || rows.length >= Number(result.total ?? rows.length)) return rows
    if (!result.rows?.length) throw new Error('分页数据不完整，请刷新后重试')
  }
  throw new Error('配置记录过多，请使用高级管理筛选')
}
