/** 与后端图片尺寸映射版本一一致；仅用于显示，后端仍独立校验。 */
export function imageSize(ratio: string, resolution: string): string {
  if (ratio === 'Auto') return 'auto'
  const edges: Record<string, number> = { '1K': 1024, '2K': 2048, '4K': 3840 }
  const ratios = ['1:1', '3:2', '2:3', '16:9', '9:16', '4:3', '3:4', '21:9']
  const edge = edges[resolution]
  if (!edge || !ratios.includes(ratio)) return ''
  const [width, height] = ratio.split(':').map(Number) as [number, number]
  const short = Math.floor((edge * Math.min(width, height) + 8 * Math.max(width, height)) / (16 * Math.max(width, height))) * 16
  return width >= height ? `${edge}x${short}` : `${short}x${edge}`
}

/** 与当前图片适配器的供应商总像素限制一致，不改变用户已有选择。 */
export function imageSizeIssue(size: string): string {
  const match = /^(\d+)x(\d+)$/.exec(size)
  if (!match) return ''
  const pixels = Number(match[1]) * Number(match[2])
  return pixels < 655360 || pixels > 8294400
    ? `当前尺寸 ${size.replace('x', ' × ')} 不符合模型总像素要求，请选择 2K 或自动比例。`
    : ''
}
