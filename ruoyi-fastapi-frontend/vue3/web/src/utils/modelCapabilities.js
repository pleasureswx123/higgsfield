/** 初始配置不宣称任何参数、媒体或估价能力，须按已核实供应商能力补齐。 */
export function emptyCapabilities() {
  return {
    variantDimensions: {},
    parametersSchema: {
      type: 'object',
      additionalProperties: false,
      properties: {},
      required: [],
      conditions: [],
    },
    referenceRules: { roles: {}, maxTotal: 0 },
    defaultParameters: {},
    presentation: {
      aliases: [],
      family: '',
      releaseLabel: '',
      market: 'unspecified',
      tier: 'unspecified',
    },
    estimatePolicy: null,
  }
}

export function parseCapabilities(text) {
  let result
  try {
    result = JSON.parse(text)
  } catch {
    throw new Error('能力配置必须为合法JSON')
  }
  const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value)
  if (!object(result)) throw new Error('能力配置必须是JSON对象')
  for (const key of ['parametersSchema', 'referenceRules'])
    if (!object(result[key])) throw new Error(`缺少对象配置：${key}`)
  function inspect(value) {
    if (
      typeof value === 'number' &&
      (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value)))
    )
      throw new Error('配置数字超出浏览器可精确表示范围')
    if (value && typeof value === 'object') for (const child of Object.values(value)) inspect(child)
  }
  inspect(result)
  return result
}
