const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
const exportsObject = {}
runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/utils/briefDocument.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: exportsObject })
const { toBriefEditor, fromBriefEditor, briefOutline, hasBriefText } = exportsObject
const plain = value => JSON.parse(JSON.stringify(value))

test('已有正文往返保留段落、换行、粗斜体和链接', () => {
  const body = { schemaVersion: 1, type: 'doc', content: [
    { type: 'paragraph', content: [{ type: 'text', text: '制作目标\n第二行🌊', marks: [{ type: 'bold' }, { type: 'italic' }] }] },
    { type: 'paragraph', content: [] },
    { type: 'paragraph', content: [{ type: 'text', text: '参考链接', marks: [{ type: 'link', href: 'https://example.com/style' }] }] },
  ] }
  assert.deepEqual(plain(fromBriefEditor(toBriefEditor(body))), body)
})
test('空文档可以编辑，清空正文恢复规范空值，软换行保留', () => {
  const empty = { schemaVersion: 1, type: 'doc', content: [] }
  assert.equal(toBriefEditor(empty).content[0].type, 'paragraph')
  assert.deepEqual(plain(fromBriefEditor(toBriefEditor(empty))), empty)
  const result = fromBriefEditor({ content: [{ content: [{ type: 'text', text: '前' }, { type: 'hardBreak' }, { type: 'text', text: '后' }] }] })
  assert.equal(result.content[0].content.map(n => n.text).join(''), '前\n后')
})
test('填写提纲独立生成，不污染下次插入内容', () => {
  const first = briefOutline()
  assert.equal(hasBriefText(first), true)
  first.content[0].content[0].text = '修改'
  assert.equal(briefOutline().content[0].content[0].text, '制作目标')
})

test('编辑器合并后的长正文按接口限制分片，不丢失字符或格式', () => {
  const text = '🌊'.repeat(30000)
  const result = fromBriefEditor({ content: [{ content: [{ type: 'text', text, marks: [{ type: 'bold' }] }] }] })
  const nodes = result.content[0].content
  assert.equal(nodes.length, 2)
  assert.equal(Array.from(nodes[0].text).length, 20000)
  assert.equal(nodes.map(node => node.text).join(''), text)
  assert.equal(nodes[1].marks[0].type, 'bold')
})
