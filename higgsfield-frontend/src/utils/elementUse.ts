import type { DraftReference, ModelCapability } from '@/api/creation'
import type { ReferenceCandidate } from '@/api/references'
import { appendCandidate, compatibleReferenceRoles, selectReferenceMedia } from './draftReferences'
import { editPrompt, type PromptDocument } from './promptDocument'

/** 先完整校验副本，调用方一次应用，不留下半批引用。 */
export function prepareElementUse(
  prompt: PromptDocument,
  references: DraftReference[],
  candidates: ReferenceCandidate[],
  model: ModelCapability | null,
) {
  let next = references.map((item) => ({ ...item }))
  const additions: { name: string; key: string }[] = []
  for (const candidate of candidates) {
    if (!candidate.elementRevisionId || !candidate.assetVersionIds.length)
      throw new Error(`${candidate.displayName}没有可引用图片，请先补图`)
    const compatible = compatibleReferenceRoles(candidate, model)
    const role = ['reference_image', 'first_frame'].find((value) => compatible.includes(value))
    if (!role) throw new Error('当前模型不支持元素图片引用，请在创作区选择兼容模型')
    let key = next.find(
      (item) => item.elementRevisionId === candidate.elementRevisionId && item.mediaRole === role,
    )?.referenceKey
    if (!key) {
      next = appendCandidate(next, selectReferenceMedia(candidate), role)
      key = next.at(-1)!.referenceKey
    }
    if (
      !prompt.content.some((block) =>
        block.content.some((node) => node.type === 'mention' && node.referenceKey === key),
      ) &&
      !additions.some((item) => item.key === key)
    )
      additions.push({ name: candidate.displayName, key })
  }
  if (model) {
    if (next.length > model.referenceRules.maxTotal)
      throw new Error('所选元素图片超过当前模型引用总数限制')
    for (const [role, rule] of Object.entries(model.referenceRules.roles)) {
      if (next.filter((item) => item.mediaRole === role).length > rule.maxCount)
        throw new Error('所选元素图片超过当前模型对应角色的数量限制')
    }
  }
  const document = editPrompt(prompt, (copy) => {
    for (const item of additions)
      copy.content.push({
        type: 'paragraph',
        content: [
          { type: 'text', text: `@${item.name} ` },
          { type: 'mention', referenceKey: item.key },
        ],
      })
  })
  return { prompt: document, references: next }
}
