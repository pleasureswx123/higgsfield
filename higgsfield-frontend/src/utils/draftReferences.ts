import type { DraftReference, ModelCapability } from '@/api/creation'
import type { ReferenceCandidate } from '@/api/references'

/** 元素默认只选主图；显式多选按修订原顺序固定，拒绝混入其他来源。 */
export function selectReferenceMedia(candidate: ReferenceCandidate, selected?: string[]): ReferenceCandidate {
  if (candidate.kind !== 'element') return candidate
  const ids = selected ?? [candidate.primaryAssetVersionId || candidate.assetVersionIds[0]!]
  if (!ids.length || ids.some(id => !id || !candidate.assetVersionIds.includes(id)))
    throw new Error('请选择当前元素修订中的有效图片')
  return { ...candidate, assetVersionIds: candidate.assetVersionIds.filter(id => ids.includes(id)) }
}

/** 候选角色对应的媒体类型沿用引用检索接口契约。 */
export function compatibleReferenceRoles(
  candidate: ReferenceCandidate,
  model?: ModelCapability | null,
): string[] {
  const mediaTypes: Record<string, string> = {
    reference_image: 'image',
    first_frame: 'image',
    reference_video: 'video',
  }
  return candidate.allowedMediaRoles.filter((role) => {
    if (!model) return true
    const rule = model.referenceRules.roles[role]
    return Boolean(rule && rule.maxCount > 0 && rule.mediaTypes.includes(mediaTypes[role] || ''))
  })
}

export function appendCandidate(
  current: DraftReference[],
  candidate: ReferenceCandidate,
  role: string,
  model?: ModelCapability | null,
): DraftReference[] {
  if (!compatibleReferenceRoles(candidate, model).includes(role))
    throw new Error('候选素材或当前模型不支持此引用角色')
  const versions =
    role === 'first_frame'
      ? [candidate.primaryAssetVersionId || candidate.assetVersionIds[0]].filter(
          (id): id is string => !!id,
        )
      : candidate.assetVersionIds
  const fresh = versions.filter(
    (id) =>
      !current.some(
        (item) =>
          item.assetVersionId === id &&
          item.mediaRole === role &&
          item.elementRevisionId === (candidate.elementRevisionId || null),
      ),
  )
  if (!fresh.length) throw new Error('所选引用已经加入草稿')
  if (current.length + fresh.length > 200) throw new Error('一份草稿最多保存200项素材引用')
  if (model) {
    if (current.length + fresh.length > model.referenceRules.maxTotal)
      throw new Error('所选素材超过当前模型引用总数限制')
    const count = current.filter((item) => item.mediaRole === role).length + fresh.length
    if (count > model.referenceRules.roles[role]!.maxCount)
      throw new Error('所选素材超过当前模型对应角色的数量限制')
  }
  const next =
    current.reduce(
      (max, item) => (BigInt(item.referenceKey) > max ? BigInt(item.referenceKey) : max),
      0n,
    ) + 1n
  if (next > 9223372036854775807n) throw new Error('引用编号已达到上限，请新建草稿')
  return [
    ...current,
    ...fresh.map((assetVersionId) => ({
      referenceKey: String(next),
      assetVersionId,
      elementRevisionId: candidate.elementRevisionId || null,
      mediaRole: role,
      ordinal: 0,
    })),
  ].map((item, ordinal) => ({ ...item, ordinal }))
}

export function moveReference(
  current: DraftReference[],
  index: number,
  offset: number,
): DraftReference[] {
  const target = index + offset
  if (target < 0 || target >= current.length) return current
  const result = [...current]
  ;[result[index], result[target]] = [result[target]!, result[index]!]
  return result.map((item, ordinal) => ({ ...item, ordinal }))
}

/** 用户确认升级后替换同一提及的固定来源，提示词引用键保持不变。 */
export function upgradeReferenceGroup(current: DraftReference[], key: string, oldRevision: string,
  candidate: ReferenceCandidate, model?: ModelCapability | null): DraftReference[] {
  const group = current.filter(item => item.referenceKey === key)
  if (!group.length || group.some(item => item.elementRevisionId !== oldRevision) ||
    candidate.kind !== 'element' || !candidate.elementRevisionId || candidate.elementRevisionId === oldRevision)
    throw new Error('引用已变化，请重新检查元素修订')
  const roles = [...new Set(group.map(item => item.mediaRole))]
  const replacements: DraftReference[] = []
  for (const role of roles) {
    if (!compatibleReferenceRoles(candidate, model).includes(role)) throw new Error('新修订与当前模型引用角色不兼容')
    const versions = role === 'first_frame' ? [candidate.primaryAssetVersionId || candidate.assetVersionIds[0]] : candidate.assetVersionIds
    if (!versions.length || versions.some(id => !id || !candidate.assetVersionIds.includes(id))) throw new Error('新修订没有可用图片')
    for (const id of new Set(versions)) replacements.push({ referenceKey: key, assetVersionId: id!,
      elementRevisionId: candidate.elementRevisionId, mediaRole: role, ordinal: 0 })
  }
  const first = current.findIndex(item => item.referenceKey === key)
  const result = current.flatMap((item, index) => item.referenceKey === key ? (index === first ? replacements : []) : [{ ...item }])
  if (result.length > 200 || (model && result.length > model.referenceRules.maxTotal)) throw new Error('升级后引用数量超过限制，原引用已保留')
  if (model && roles.some(role => result.filter(item => item.mediaRole === role).length > model.referenceRules.roles[role]!.maxCount))
    throw new Error('升级后该角色图片数量超过当前模型限制，原引用已保留')
  return result.map((item, ordinal) => ({ ...item, ordinal }))
}
