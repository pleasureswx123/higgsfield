import type { DraftReference, ModelCapability, ParameterRule, Scalar } from '@/api/creation'

function accepts(rule: ParameterRule, value: Scalar): boolean {
  if (rule.enum && !rule.enum.includes(value)) return false
  if (rule.type === 'boolean') return typeof value === 'boolean'
  if (rule.type === 'string') return typeof value === 'string' &&
    (rule.minLength == null || [...value].length >= rule.minLength) &&
    (rule.maxLength == null || [...value].length <= rule.maxLength)
  return typeof value === 'number' && Number.isFinite(value) &&
    (rule.type !== 'integer' || Number.isInteger(value)) &&
    (rule.minimum == null || value >= rule.minimum) &&
    (rule.maximum == null || value <= rule.maximum)
}

/** 只比较客户端已知能力；引用授权和实际媒体规格仍由服务端预检。 */
export function modelTransition(
  model: ModelCapability | null,
  parameters: Record<string, Scalar>,
  references: DraftReference[],
) {
  const next = { ...(model?.defaultParameters || {}) }
  const incompatible: string[] = []
  for (const [name, value] of Object.entries(parameters)) {
    const rule = model?.parametersSchema.properties[name]
    if (rule && accepts(rule, value)) next[name] = value
    else incompatible.push(name)
  }
  const warnings: string[] = []
  if (incompatible.length) warnings.push(`参数 ${incompatible.join('、')} 不适用于目标模型，将使用目标默认值或留空。`)
  if (model) {
    if (references.length > model.referenceRules.maxTotal) warnings.push('已有引用超过目标模型总数上限。')
    const types: Record<string, string> = { reference_image: 'image', first_frame: 'image', reference_video: 'video' }
    const counts = new Map<string, number>()
    for (const item of references) counts.set(item.mediaRole, (counts.get(item.mediaRole) || 0) + 1)
    for (const [role, count] of counts) {
      const rule = model.referenceRules.roles[role]
      if (!rule || !rule.mediaTypes.includes(types[role] || '') || count > rule.maxCount)
        warnings.push(`已有 ${role} 引用与目标模型不兼容。`)
    }
  }
  return { parameters: next, warnings }
}
