import type { JSONContent } from '@tiptap/vue-3'
import type { Transaction } from '@tiptap/pm/state'
import type { DraftReference, PromptNode } from '@/api/creation'
import { editPrompt, type PromptDocument } from './promptDocument'

/** 全选包含段落边界，粘贴位置须由插入后的正文光标计算。 */
export function insertPromptText(transaction: Transaction, text: string) {
  transaction.insertText(text)
  return { transaction, start: transaction.selection.from - text.length }
}

/** 最后一处提及消失时释放引用；手动添加、尚未写入提示词的素材保持不变。 */
export function reconcilePromptReferences(
  before: JSONContent,
  after: JSONContent,
  references: DraftReference[],
  retained: DraftReference[] = [],
) {
  const keysOf = (document: JSONContent) =>
    new Set(
      (document.content ?? []).flatMap((paragraph) =>
        (paragraph.content ?? []).flatMap((node) =>
          node.type === 'mention' ? [String(node.attrs?.id)] : [],
        ),
      ),
    )
  const previous = keysOf(before),
    current = keysOf(after)
  const next = references.filter(
    (item) => !previous.has(item.referenceKey) || current.has(item.referenceKey),
  )
  // 撤销剪切时恢复原固定版本，不能留下只有标签、没有图片的引用。
  for (const key of current)
    if (!next.some((item) => item.referenceKey === key))
      next.push(...retained.filter((item) => item.referenceKey === key))
  return next.map((item, ordinal) => ({ ...item, ordinal }))
}

/** 删除引用及其显示名称，保留前后正文。 */
export function removePromptReference(
  document: PromptDocument,
  references: DraftReference[],
  key: string,
) {
  const content = toEditorDocument(document)
  const remaining = references.filter(item => item.referenceKey !== key)
  const labels = referenceNumberLabels(remaining)
  for (const paragraph of content.content ?? [])
    paragraph.content = paragraph.content?.filter(
      (node) => node.type !== 'mention' || node.attrs?.id !== key,
    ).map(node => node.type === 'mention' && labels.has(String(node.attrs?.id))
      ? { ...node, attrs: { ...node.attrs, label: labels.get(String(node.attrs?.id)) } } : node)
  return fromEditorDocument(content, remaining)
}

/** 素材按当前引用顺序连续编号，元素保持自己的名字，引用键和固定版本不变。 */
export function referenceNumberLabels(references: DraftReference[]) {
  const labels = new Map<string, string>()
  let image = 0, video = 0
  for (const item of references) {
    if (item.elementRevisionId || labels.has(item.referenceKey)) continue
    labels.set(item.referenceKey, item.mediaRole === 'reference_video' ? `Video ${++video}` : `Image ${++image}`)
  }
  return labels
}

/** 沿用后端的「名称正文 + 引用键」契约，在编辑器中合并显示为一个行内标签。 */
export function toEditorDocument(document: PromptDocument): JSONContent {
  return {
    type: 'doc',
    content: document.content.length
      ? document.content.map((paragraph) => {
          const content: JSONContent[] = []
          for (const node of paragraph.content) {
            if (node.type === 'text') {
              if (node.text)
                content.push({
                  type: 'text',
                  text: node.text,
                  ...(node.marks?.length
                    ? {
                        marks: node.marks.map((mark) => ({
                          type: mark.type,
                          ...(mark.type === 'link' ? { attrs: { href: mark.href } } : {}),
                        })),
                      }
                    : {}),
                })
            } else {
              const previous = content.at(-1)
              const match =
                previous?.type === 'text'
                  ? previous.text?.startsWith('@')
                    ? /^@([\s\S]+) $/u.exec(previous.text)
                    : /@([^@\n]+) $/u.exec(previous.text || '')
                  : null
              const label = match?.[1] || '已引用元素'
              if (match && previous) {
                previous.text = previous.text!.slice(0, match.index)
                if (!previous.text) content.pop()
              }
              content.push({ type: 'mention', attrs: { id: node.referenceKey, label } })
            }
          }
          return { type: 'paragraph', content }
        })
      : [{ type: 'paragraph' }],
  }
}

/** 只输出现有接口允许的节点；外来标签没有本草稿引用时降为名称文本。 */
export function fromEditorDocument(
  document: JSONContent,
  references: DraftReference[],
): PromptDocument {
  const keys = new Set(references.map((item) => item.referenceKey))
  const content = (document.content || []).map((paragraph) => {
    const nodes: PromptNode[] = []
    for (const node of paragraph.content || []) {
      if (node.type === 'mention') {
        const key = String(node.attrs?.id || '')
        nodes.push({ type: 'text', text: `@${String(node.attrs?.label || '已引用元素')} ` })
        if (keys.has(key)) nodes.push({ type: 'mention', referenceKey: key })
      } else if (node.type === 'text' || node.type === 'hardBreak') {
        const text = node.type === 'hardBreak' ? '\n' : node.text || ''
        const marks = node.marks
          ?.filter((mark) => ['bold', 'italic', 'link'].includes(mark.type))
          .map((mark) => ({
            type: mark.type as 'bold' | 'italic' | 'link',
            ...(mark.type === 'link' ? { href: mark.attrs?.href } : {}),
          }))
        for (const chunk of [...text].join('').match(/[\s\S]{1,20000}/gu) || [])
          nodes.push({ type: 'text', text: chunk, ...(marks?.length ? { marks } : {}) })
      }
    }
    return { type: 'paragraph' as const, content: nodes }
  })
  return editPrompt(
    {
      schemaVersion: 1,
      type: 'doc',
      content: content.length ? content : [{ type: 'paragraph', content: [] }],
    },
    () => {},
  )
}
