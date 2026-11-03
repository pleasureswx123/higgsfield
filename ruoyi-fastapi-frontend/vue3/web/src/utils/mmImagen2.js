/** 用户确认的供应商能力预设；价格和凭据由各自管理入口维护。 */
export function mmImagen2Capabilities() {
  return {
    variantDimensions: {},
    parametersSchema: {
      type: 'object', additionalProperties: false,
      properties: {
        aspect_ratio: { type: 'string', enum: ['Auto', '1:1', '3:2', '2:3', '16:9', '9:16', '4:3', '3:4', '21:9'] },
        resolution: { type: 'string', enum: ['1K', '2K', '4K'] },
        quality: { type: 'string', enum: ['auto', 'low', 'medium', 'high'] },
        n: { type: 'integer', minimum: 1, maximum: 4 },
        output_format: { type: 'string', enum: ['png', 'jpeg', 'webp'] },
        output_compression: { type: 'integer', minimum: 0, maximum: 100 },
        moderation: { type: 'string', enum: ['auto'] },
      },
      required: ['aspect_ratio', 'resolution', 'quality', 'n', 'output_format'], conditions: [],
    },
    referenceRules: { roles: { reference_image: { mediaTypes: ['image'], minCount: 0, maxCount: 16 } }, maxTotal: 16 },
    defaultParameters: { aspect_ratio: 'Auto', resolution: '2K', quality: 'high', n: 1, output_format: 'png', moderation: 'auto' },
    presentation: { aliases: ['mm-imagen2'], family: 'gpt-image-2', releaseLabel: '尺寸映射 v1', market: 'unspecified', tier: 'standard' },
    estimatePolicy: null,
  }
}
