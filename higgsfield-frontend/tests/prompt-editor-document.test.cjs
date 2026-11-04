const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript')
function load(name) {
  const exports = {}
  runInNewContext(
    ts.transpileModule(readFileSync(join(__dirname, '../src/utils', name + '.ts'), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    { exports, Error, require: (id) => load(id.replace('./', '')) },
  )
  return exports
}
const { toEditorDocument, fromEditorDocument, removePromptReference, reconcilePromptReferences } = load('promptEditorDocument')
const refs = [
  {
    referenceKey: '123456789012345678',
    assetVersionId: '7',
    elementRevisionId: '2',
    mediaRole: 'reference_image',
    ordinal: 0,
  },
]
const original = {
  schemaVersion: 1,
  type: 'doc',
  content: [
    {
      type: 'paragraph',
      content: [
        { type: 'text', text: '镜头前 @女主角 ' },
        { type: 'mention', referenceKey: refs[0].referenceKey },
        { type: 'text', text: ' 走向镜头', marks: [{ type: 'bold' }] },
      ],
    },
  ],
}
const json = (value) => JSON.parse(JSON.stringify(value))
test('历史名称正文与引用合成行内标签，前后文字仍在同一段落', () => {
  const editor = toEditorDocument(original)
  assert.equal(editor.content.length, 1)
  assert.equal(editor.content[0].content[0].text, '镜头前 ')
  assert.equal(editor.content[0].content[1].attrs.label, '女主角')
  assert.equal(editor.content[0].content[2].text, ' 走向镜头')
  assert.equal(original.content[0].content[0].text, '镜头前 @女主角 ')
})
test('保存重载保持元素名称、字符串引用键与正文标记', () => {
  const editor = toEditorDocument(original)
  const restored = toEditorDocument(fromEditorDocument(editor, refs))
  assert.deepEqual(json(restored), json(editor))
  assert.equal(restored.content[0].content[1].attrs.id, refs[0].referenceKey)
})
test('删除标签只移除当前提及，其他同名引用及正文不变', () => {
  const editor = toEditorDocument(original)
  editor.content[0].content.splice(1, 1)
  const result = fromEditorDocument(editor, refs)
  assert.equal(
    result.content[0].content.some((node) => node.type === 'mention'),
    false,
  )
  assert.equal(result.content[0].content.map((node) => node.text).join(''), '镜头前  走向镜头')
  assert.equal(refs.length, 1)
})
test('外部未知引用降为文字，不能制造未关联的引用键', () => {
  const editor = toEditorDocument(original)
  editor.content[0].content[1].attrs.id = '999'
  const result = fromEditorDocument(editor, refs)
  assert.equal(
    result.content[0].content.some((node) => node.type === 'mention'),
    false,
  )
  assert.match(result.content[0].content.map((node) => node.text).join(''), /@女主角/)
})
test('换行、中文与长文本保持内容，超限拒绝写入', () => {
  const content = {
    type: 'doc',
    content: [
      {
        type: 'paragraph',
        content: [
          { type: 'text', text: '中'.repeat(20001) },
          { type: 'hardBreak' },
          { type: 'text', text: '尾' },
        ],
      },
    ],
  }
  const result = fromEditorDocument(content, [])
  assert.equal(
    result.content[0].content.map((node) => node.text).join(''),
    '中'.repeat(20001) + '\n尾',
  )
  content.content[0].content = [{ type: 'text', text: '中'.repeat(50001) }]
  assert.throws(() => fromEditorDocument(content, []), /总长度/)
})

test('名称包含空格、@ 或换行仍能准确恢复为单个标签', () => {
  for (const label of ['角色 A', '角色@版本2', '第一行\n第二行']) {
    const editor = {
      type: 'doc',
      content: [
        {
          type: 'paragraph',
          content: [{ type: 'mention', attrs: { id: refs[0].referenceKey, label } }],
        },
      ],
    }
    assert.equal(
      toEditorDocument(fromEditorDocument(editor, refs)).content[0].content[0].attrs.label,
      label,
    )
  }
})

test('删除缩略图同时清理所有同键标签及名称，保留正文', () => {
  const document = JSON.parse(JSON.stringify(original))
  document.content[0].content.push({ type: 'text', text: ' @女主角 ' }, { type: 'mention', referenceKey: refs[0].referenceKey })
  const result = removePromptReference(document, [], refs[0].referenceKey)
  assert.equal(result.content[0].content.some(node => node.type === 'mention'), false)
  const text = result.content[0].content.map(node => node.text || '').join('')
  assert.equal(text.includes('女主角'), false)
  assert.equal(text.includes('镜头前'), true)
  assert.equal(text.includes('走向镜头'), true)
})

test('剪切最后一处标签移除该引用，重复提及仍保留，未提及的手动素材不受影响', () => {
  const before = toEditorDocument(original)
  const key = refs[0].referenceKey
  before.content[0].content.push({ type: 'mention', attrs: { id: key, label: '女主角' } })
  const manual = { ...refs[0], referenceKey: '9', assetVersionId: '8', elementRevisionId: null, ordinal: 1 }
  const afterOne = JSON.parse(JSON.stringify(before))
  afterOne.content[0].content.pop()
  assert.equal(reconcilePromptReferences(before, afterOne, [...refs, manual]).length, 2)
  const afterAll = { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '保留正文' }] }] }
  const result = reconcilePromptReferences(before, afterAll, [...refs, manual])
  assert.equal(result.length, 1)
  assert.equal(result[0].referenceKey, '9')
  assert.equal(result[0].ordinal, 0)
  assert.equal(refs.length, 1)
})
test('撤销剪切可恢复原固定版本与多个提及的共同引用', () => {
  const empty = { type: 'doc', content: [{ type: 'paragraph' }] }
  const result = reconcilePromptReferences(empty, toEditorDocument(original), [], refs)
  assert.equal(result.length, 1)
  assert.equal(result[0].assetVersionId, '7')
  assert.equal(result[0].referenceKey, refs[0].referenceKey)
})

test('全选替换与跨段替换粘贴使用实际正文起点，标签不吃标点、不残留尾字', () => {
  const { Schema } = require('@tiptap/pm/model')
  const { EditorState, AllSelection, TextSelection } = require('@tiptap/pm/state')
  const { insertPromptText } = load('promptEditorDocument')
  const schema = new Schema({ nodes: {
    doc: { content: 'paragraph+' }, paragraph: { content: 'inline*', group: 'block' },
    text: { group: 'inline' }, mention: { inline: true, group: 'inline', atom: true, attrs: { label: {} } },
  } })
  const doc = schema.node('doc', null, [schema.node('paragraph', null, schema.text('旧正文')), schema.node('paragraph', null, schema.text('后段'))])
  const text = '开场：@下载+(1) 走入，@woman 转身。'
  for (const selection of [new AllSelection(doc), TextSelection.create(doc, 2, doc.content.size - 1)]) {
    const state = EditorState.create({ schema, doc, selection })
    const { transaction, start } = insertPromptText(state.tr, text)
    assert.equal(transaction.doc.textBetween(start, start + text.length), text)
    for (const match of [...text.matchAll(/@([^\s，。]+)/gu)].reverse())
      transaction.replaceWith(start + match.index, start + match.index + match[0].length, schema.nodes.mention.create({ label: match[1] }))
    assert.equal(transaction.doc.textContent.includes('n 转身'), false)
    assert.equal(transaction.doc.textContent.includes(') 走入'), false)
    assert.equal(transaction.doc.textContent.includes('开场：'), true)
  }
})

test('异步标签识别与粘贴作为一次撤销和重做，不经过普通文本中间态', () => {
  const { Schema } = require('@tiptap/pm/model')
  const { EditorState } = require('@tiptap/pm/state')
  const { history, closeHistory, undo, redo } = require('@tiptap/pm/history')
  const { insertPromptText } = load('promptEditorDocument')
  const schema = new Schema({ nodes: {
    doc: { content: 'paragraph+' }, paragraph: { content: 'inline*', group: 'block' },
    text: { group: 'inline' }, mention: { inline: true, group: 'inline', atom: true, attrs: { label: {} } },
  } })
  let state = EditorState.create({ schema, plugins: [history()] })
  const { transaction, start } = insertPromptText(closeHistory(state.tr), '场景 @woman')
  state = state.apply(transaction)
  const resolved = state.tr.setTime(transaction.time).replaceWith(start + 3, start + 9, schema.nodes.mention.create({ label: 'woman' }))
  state = state.apply(resolved)
  state = state.apply(closeHistory(state.tr))
  const result = state.doc.toJSON()
  assert.equal(undo(state, tr => { state = state.apply(tr) }), true)
  assert.equal(state.doc.textContent, '')
  assert.equal(redo(state, tr => { state = state.apply(tr) }), true)
  assert.deepEqual(state.doc.toJSON(), result)
})
