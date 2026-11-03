/** 列表仅陈述已保存状态；不把发布或路由配置等同于供应商实时可用。 */
import { findVideoModel } from './videoModels.js'
export function modelHubState(model, versions, routes) {
  const supported = model.code === 'mm-imagen2' && model.kind === 'image' || model.kind === 'video' && !!findVideoModel(model.code)
  const published = versions.filter(row => row.status === 'published')
  const enabled = published.length > 0 && routes?.some(row => row.modelId === model.id && row.enabled && row.credentials.length)
  if (enabled) return { label: '已配置全平台使用', tone: 'success', supported, next: '可前往制作端验证生成，也可查看当前配置。' }
  if (published.length && routes?.some(row => row.modelId === model.id) && !routes.some(row => row.modelId === model.id && row.enabled)) return { label: '已停用', tone: 'info', supported, next: '配置已保留，可直接重新启用，无需重复测试。' }
  if (routes === null && published.length) return { label: '开放状态未读取', tone: 'info', supported, next: '刷新状态或检查全平台配置权限。' }
  if (versions.length && versions.every(row => row.status === 'disabled'))
    return { label: '已停用', tone: 'info', supported, next: '原配置已保留，重新接入需配置新的能力版本。' }
  if (!supported) return { label: '待适配', tone: 'warning', supported, next: findVideoModel(model.code)
    ? '已识别供应商视频模型，视频测试与启用流程尚未接通，当前不会发起付费测试。'
    : '请提供该模型的接口与计费文档，确认适配后再测试启用。' }
  return { label: published.length ? '待全平台启用' : '待完成配置', tone: 'warning', supported,
    next: published.length ? '已有发布版本，继续确认价格并启用到全平台。' : '继续确认模型能力、价格和测试结果。已有记录会复用。' }
}

export function toggleModelRoutes(config, modelId, enabled) {
  if (!config.routes.some(row => row.modelId === modelId)) throw new Error('请先完成模型配置')
  return { revision: config.revision, routes: config.routes.map(row => ({ ...row, enabled: row.modelId === modelId ? enabled : row.enabled })) }
}
