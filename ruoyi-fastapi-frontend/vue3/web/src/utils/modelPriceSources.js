/** 兼容历史文字和结构化依据，只展示明确属于当前模型的来源。 */
export function modelPriceSources(rows, model) {
  return rows.flatMap(row => {
    const excerpt = String(row.excerpt || '').trim()
    let data
    try { data = JSON.parse(excerpt) } catch { /* 历史中文依据按模型标识匹配。 */ }
    const models = excerpt.match(/mm-[a-z0-9]+(?:[.-][a-z0-9]+)*/gi) || []
    if (data?.model ? data.model !== model : !models.includes(model)) return []
    if (!data || typeof data !== 'object') {
      return [{ ...row, label: excerpt.replace(/\s+/g, ' ').slice(0, 90), description: excerpt }]
    }
    const parts = [`${model} 供应商价格确认`]
    if (data.exchangeRate) parts.push(`汇率：1 USD = ${data.exchangeRate} CNY`)
    if (Array.isArray(data.prices)) for (const price of data.prices) {
      parts.push(`${price.resolution}：含参考视频 ${price.withVideo}，无参考视频 ${price.withoutVideo} CNY / 百万输出 Token`)
    }
    return [{ ...row, label: `${model} · 供应商价格确认（依据 ${row.id}）`, description: parts.join('；') }]
  })
}
