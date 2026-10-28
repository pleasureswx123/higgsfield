import type { DraftBody, PromptNode } from '@/api/creation'
export type PromptDocument = DraftBody['prompt']
export function promptText(body: PromptDocument): string {
  return body.content
    .map((paragraph) =>
      paragraph.content.map((node) => (node.type === 'text' ? node.text : '[引用]')).join(''),
    )
    .join('\n')
}
export function editPrompt(
  body: PromptDocument,
  edit: (copy: PromptDocument) => void,
): PromptDocument {
  const copy: PromptDocument = JSON.parse(JSON.stringify(body))
  edit(copy)
  if (copy.content.length > 200 || copy.content.some((paragraph) => paragraph.content.length > 100))
    throw new Error('最多200个段落，每段最多100个文本或引用片段')
  const nodes = copy.content.flatMap((paragraph) => paragraph.content)
  if (nodes.some((node) => node.type === 'text' && [...node.text].length > 20000))
    throw new Error('单个文本片段最多20000字符')
  if (
    nodes.reduce((size, node) => size + (node.type === 'text' ? [...node.text].length : 0), 0) >
    50000
  )
    throw new Error('提示词总长度不能超过50000字符')
  return copy
}
export function insertPromptNode(
  body: PromptDocument,
  block: number,
  after: number,
  node: PromptNode,
): PromptDocument {
  return editPrompt(body, (copy) => {
    if (!copy.content.length) copy.content.push({ type: 'paragraph', content: [] })
    const paragraph = copy.content[Math.min(Math.max(block, 0), copy.content.length - 1)]!
    paragraph.content.splice(Math.min(Math.max(after + 1, 0), paragraph.content.length), 0, node)
  })
}
