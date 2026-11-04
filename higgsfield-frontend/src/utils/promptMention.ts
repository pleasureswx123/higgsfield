import type { DraftReference, ModelCapability, PromptNode } from '@/api/creation'
import type { ReferenceCandidate } from '@/api/references'
import { appendCandidate, compatibleReferenceRoles } from './draftReferences'
import { editPrompt, type PromptDocument } from './promptDocument'

export interface PromptCursor {
  block: number
  index: number
  start: number
  end: number
}

/** 多个粘贴提及必须累计引用后一次提交，不能依赖尚未刷新的组件 props。 */
export function prepareMentionBatch(
  references: DraftReference[],
  candidates: ReferenceCandidate[],
  model: ModelCapability | null | undefined,
) {
  let next = references
  const keys: string[] = []
  for (const candidate of candidates) {
    if (candidate.kind === 'asset') {
      if (!next.some((item) => item.referenceKey === candidate.id))
        throw new Error('此素材已被移除')
      keys.push(candidate.id)
    } else {
      const result = prepareMentionReference(next, candidate, model)
      next = result.references
      keys.push(result.key)
    }
  }
  return { references: next, keys }
}

/** 两个入口共用原子插入：验证成功后才同时应用提示词和固定版本引用。 */
export function insertElementMention(
  document: PromptDocument,
  references: DraftReference[],
  candidate: ReferenceCandidate,
  model: ModelCapability | null | undefined,
  cursor: PromptCursor,
  role = compatibleReferenceRoles(candidate, model)[0],
) {
  const { references: next, key } = prepareMentionReference(references, candidate, model, role)
  const prompt = editPrompt(document, (copy) => {
    const paragraph = copy.content[cursor.block]
    if (!paragraph) throw new Error('提示词已变化，请重新选择插入位置')
    const node = paragraph.content[cursor.index]
    if (node && node.type !== 'text') throw new Error('插入位置已变化，请重新选择')
    const text = node?.text ?? ''
    if (cursor.start < 0 || cursor.end < cursor.start || cursor.end > text.length)
      throw new Error('插入位置已变化，请重新选择')
    const parts: PromptNode[] = [
      { ...node, type: 'text', text: text.slice(0, cursor.start) + `@${candidate.displayName} ` },
      { type: 'mention', referenceKey: key },
      { ...node, type: 'text', text: text.slice(cursor.end) || ' ' },
    ]
    paragraph.content.splice(cursor.index, node ? 1 : 0, ...parts)
  })
  return { prompt, references: next }
}

/** 编辑器和工具栏共用的固定版本引用校验。 */
export function prepareMentionReference(
  references: DraftReference[],
  candidate: ReferenceCandidate,
  model: ModelCapability | null | undefined,
  role = compatibleReferenceRoles(candidate, model)[0],
) {
  if (
    candidate.kind !== 'element' ||
    !candidate.elementRevisionId ||
    !candidate.assetVersionIds.length
  )
    throw new Error('该元素没有可引用图片，请先补图')
  if (!role || !compatibleReferenceRoles(candidate, model).includes(role))
    throw new Error('当前模型不支持此元素的引用角色，请更换模型')
  const existing = references.find(
    (item) =>
      item.elementRevisionId === candidate.elementRevisionId &&
      item.mediaRole === role &&
      candidate.assetVersionIds.includes(item.assetVersionId),
  )
  const complete = candidate.assetVersionIds.every((id) =>
    references.some(
      (item) =>
        item.elementRevisionId === candidate.elementRevisionId &&
        item.mediaRole === role &&
        item.assetVersionId === id,
    ),
  )
  let next = complete ? references : appendCandidate(references, candidate, role, model)
  const key = existing?.referenceKey ?? next.at(-1)!.referenceKey
  if (existing && !complete) {
    const addedKey = next.at(-1)!.referenceKey
    next = next.map((item) =>
      item.referenceKey === addedKey ? { ...item, referenceKey: key } : item,
    )
  }
  return { references: next, key }
}
