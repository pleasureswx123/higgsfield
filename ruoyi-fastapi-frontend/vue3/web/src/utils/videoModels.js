/** 供应商视频模型目录；登记不等于已经完成测试或启用。 */
export const videoModels = [
  ...['eva', 'nova'].flatMap(market => ['2.0', '2.5'].flatMap(version => [false, true].map(fast => {
    const alias = `mm-${market}-sd-${version}${fast ? '-fast' : ''}`
    return {
      alias, code: alias.replaceAll('.', '-'), kind: 'video',
      name: `SD ${version}${fast ? ' 快速版' : ' 标准版'} · ${market === 'eva' ? '国际站' : '国内站'}`,
      market, resolutions: fast ? ['480p', '720p'] : ['480p', '720p', '1080p'],
    }
  }))),
  { alias: 'mm-h3', code: 'mm-h3', kind: 'video', name: 'H3 · 国际站', market: 'eva', resolutions: ['2K'] },
]

export function findVideoModel(code) {
  return videoModels.find(model => model.code === code || model.alias === code)
}

/** SD 单价保留人民币基准，通过计价基数精确表达除以 6.69，不提前舍入美元。 */
export function sdPriceItems(alias, resolution, hasVideo) {
  if (alias === 'mm-h3') return [
    { itemCode: 'output_seconds', unit: 'second', unitQuantity: '1', unitPrice: '0.13', formulaTemplate: 'linear', quantityFrom: '0', quantityTo: null, freeReason: null },
    { itemCode: 'input_images', unit: 'image', unitQuantity: '1', unitPrice: '0', formulaTemplate: 'tiered', quantityFrom: '0', quantityTo: '5', freeReason: '前五张输入图片免费' },
    { itemCode: 'input_images', unit: 'image', unitQuantity: '1', unitPrice: '0.04', formulaTemplate: 'tiered', quantityFrom: '5', quantityTo: null, freeReason: null },
  ]
  const version = alias.includes('2.5') ? '2.5' : '2.0'
  const fast = alias.endsWith('-fast')
  const table = {
    '2.5': { normal: [42, 70], hd: [46, 77] },
    '2.5-fast': { normal: [38, 64], hd: [42, 71] },
    '2.0': { normal: [28, 46], hd: [31, 51], uhd: [16, 26] },
    '2.0-fast': { normal: [22, 37] },
  }
  const price = table[version + (fast ? '-fast' : '')][resolution === '1080p' ? 'hd' : resolution === '4K' ? 'uhd' : 'normal']
  if (!price) throw new Error('此规格没有供应商报价')
  return [{ itemCode: 'video_tokens', unit: 'token', unitQuantity: '6690000', unitPrice: String(price[hasVideo ? 0 : 1]),
    formulaTemplate: 'linear', quantityFrom: '0', quantityTo: null, freeReason: null }]
}

export function sdCapabilities(model) {
  const resolution = { type: 'string', enum: model.resolutions }
  const result = {
    variantDimensions: { resolution, has_video_input: { type: 'boolean' } },
    parametersSchema: { type: 'object', additionalProperties: false, properties: {
      resolution, duration: { type: 'integer', enum: [-1, ...Array.from({ length: 12 }, (_, i) => i + 4)] },
      ratio: { type: 'string', enum: ['adaptive', '16:9', '9:16', '4:3', '3:4', '1:1', '21:9'] },
      generate_audio: { type: 'boolean' }, bitrate_mode: { type: 'string', enum: ['standard', 'high'] },
      seed: { type: 'integer', minimum: -1, maximum: 2147483647 }, watermark: { type: 'boolean' },
      return_last_frame: { type: 'boolean' },
    }, required: ['resolution', 'duration', 'ratio'], conditions: [] },
    referenceRules: { roles: {
      reference_image: { mediaTypes: ['image'], maxCount: 9 },
      reference_person: { mediaTypes: ['image'], maxCount: 9 },
      first_frame: { mediaTypes: ['image'], maxCount: 1 },
      reference_video: { mediaTypes: ['video'], maxCount: 3 },
    }, maxTotal: 15 },
    defaultParameters: { resolution: '720p', duration: 5, ratio: '16:9', generate_audio: true, bitrate_mode: 'standard' },
    presentation: { aliases: [model.alias], family: 'SD', market: model.market === 'eva' ? 'overseas' : 'domestic',
      tier: model.alias.endsWith('-fast') ? 'fast' : 'standard', releaseLabel: '视频接入 v1' }, estimatePolicy: null,
  }
  if (model.alias === 'mm-h3') {
    result.variantDimensions = {}
    result.parametersSchema.properties.duration = { type: 'integer', minimum: 4, maximum: 15 }
    delete result.parametersSchema.properties.generate_audio
    delete result.parametersSchema.properties.bitrate_mode
    delete result.parametersSchema.properties.seed
    delete result.parametersSchema.properties.watermark
    delete result.parametersSchema.properties.return_last_frame
    delete result.referenceRules.roles.reference_person
    result.referenceRules.roles.last_frame = { mediaTypes: ['image'], maxCount: 1 }
    result.defaultParameters = { resolution: '2K', duration: 5, ratio: '16:9' }
    result.presentation.family = 'H3'
  }
  return result
}

/** 编辑报价使用十进制文本；汇率乘百万后为整数，避免先舍入美元单价。 */
export function editedVideoItems(alias, dimensions, form) {
  const positive = value => {
    const text = String(value).trim()
    if (!/^(0|[1-9]\d{0,7})(\.\d{1,10})?$/.test(text) || !/[1-9]/.test(text)) throw new Error('价格须为大于零的数字，最多 10 位小数')
    return text
  }
  if (alias === 'mm-h3') {
    const items = sdPriceItems(alias)
    items[0].unitPrice = positive(form.secondPrice)
    items[2].unitPrice = positive(form.extraImagePrice)
    return items
  }
  const rate = String(form.exchangeRate).trim()
  if (!/^(0|[1-9]\d{0,3})(\.\d{1,6})?$/.test(rate) || !/[1-9]/.test(rate)) throw new Error('汇率须大于零，最多 6 位小数')
  const [whole, fraction = ''] = rate.split('.')
  const quantity = String(BigInt(whole) * 1000000n + BigInt(fraction.padEnd(6, '0')))
  const row = form.videoPrices.find(row => row.resolution === dimensions.resolution)
  if (!row) throw new Error('缺少此分辨率的价格')
  const items = sdPriceItems(alias, dimensions.resolution, dimensions.has_video_input)
  items[0].unitPrice = positive(dimensions.has_video_input ? row.withVideo : row.withoutVideo)
  items[0].unitQuantity = quantity
  return items
}
