import type { JSONContent } from '@tiptap/vue-3'
import type { BriefBody, TextMark } from '@/api/projectWorkspace'

export const hasBriefText = (body: BriefBody) => body.content.some(p => p.content.some(n => n.text.trim()))

export function toBriefEditor(body: BriefBody): JSONContent {
  return { type: 'doc', content: body.content.length ? body.content.map(p => ({
    type: 'paragraph', content: p.content.filter(n => n.text).map(n => ({
      type: 'text', text: n.text, marks: n.marks.map(m => m.type === 'link'
        ? { type: 'link', attrs: { href: m.href } } : { type: m.type }),
    })),
  })) : [{ type: 'paragraph' }] }
}
export function fromBriefEditor(doc: JSONContent): BriefBody {
  const body: BriefBody = { schemaVersion: 1, type: 'doc', content: (doc.content || []).map(p => ({
    type: 'paragraph', content: (p.content || []).flatMap(n => {
      const marks = (n.marks || []).filter(m => ['bold', 'italic', 'link'].includes(m.type)).map(m =>
        m.type === 'link' ? { type: 'link', href: m.attrs?.href } : { type: m.type }) as TextMark[]
      // 编辑器会合并相邻同格式文本；按接口上限分片，避免已有长正文编辑后无法保存。
      const characters = Array.from(n.type === 'hardBreak' ? '\n' : n.text || '')
      const nodes: BriefBody['content'][number]['content'] = []
      for (let start = 0; start < characters.length; start += 20000)
        nodes.push({ type: 'text', text: characters.slice(start, start + 20000).join(''), marks })
      return nodes
    }),
  })) }
  return hasBriefText(body) ? body : { ...body, content: [] }
}
export function briefOutline(): BriefBody {
  return { schemaVersion: 1, type: 'doc', content: ['制作目标', '视觉风格', '交付要求', '注意事项'].flatMap(text => [
    { type: 'paragraph' as const, content: [{ type: 'text' as const, text, marks: [{ type: 'bold' as const }] }] },
    { type: 'paragraph' as const, content: [] },
  ]) }
}
