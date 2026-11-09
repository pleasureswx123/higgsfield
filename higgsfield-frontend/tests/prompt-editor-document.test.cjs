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

test('后加图片将手写编号绑定为固定版本引用，元素和视频不占图片编号', () => {
  const { Schema } = require('@tiptap/pm/model')
  const { EditorState } = require('@tiptap/pm/state')
  const { bindNumberedMediaReferences } = load('promptEditorDocument')
  const schema = new Schema({ nodes: {
    doc: { content: 'paragraph+' }, paragraph: { content: 'inline*', group: 'block' },
    text: { group: 'inline' }, mention: { inline: true, group: 'inline', atom: true, attrs: { id: {}, label: {} } },
  } })
  const image = { referenceKey: 'scene', assetVersionId: '9007199254740993', elementRevisionId: null, mediaRole: 'reference_image', ordinal: 2 }
  const references = [...refs, { ...image, referenceKey: 'video', mediaRole: 'reference_video' }, image]
  const doc = schema.node('doc', null, [schema.node('paragraph', null, [
    schema.nodes.mention.create({ id: refs[0].referenceKey, label: 'woman' }),
    schema.text(' @Image 1，沿用@image 1；@Image 10 @Image 2 @Image 1abc @@Image 1 @Image 01'),
  ])])
  const state = EditorState.create({ schema, doc })
  assert.equal(bindNumberedMediaReferences(state.tr, refs).docChanged, false)
  const bound = bindNumberedMediaReferences(state.tr, references)
  const result = fromEditorDocument(bound.doc.toJSON(), references)
  assert.deepEqual(json(result.content[0].content.filter(n => n.type === 'mention').map(n => n.referenceKey)), [refs[0].referenceKey, 'scene', 'scene'])
  assert.match(bound.doc.textContent, /@Image 10 @Image 2 @Image 1abc @@Image 1 @Image 01/)
  assert.equal(image.assetVersionId, '9007199254740993')
  assert.equal(bindNumberedMediaReferences(state.apply(bound).tr, references).docChanged, false)
  assert.equal(toEditorDocument(result).content[0].content[0].attrs.label, 'woman')
})
test('视频编号独立绑定且不误匹配长编号，保存恢复后保持视频身份', () => {
  const { Schema } = require('@tiptap/pm/model')
  const { EditorState } = require('@tiptap/pm/state')
  const { bindNumberedMediaReferences } = load('promptEditorDocument')
  const schema = new Schema({ nodes: {
    doc: { content: 'paragraph+' }, paragraph: { content: 'inline*', group: 'block' },
    text: { group: 'inline' }, mention: { inline: true, group: 'inline', atom: true, attrs: { id: {}, label: {} } },
  } })
  const image = { referenceKey: 'image', assetVersionId: '8', elementRevisionId: null, mediaRole: 'reference_image', ordinal: 1 }
  const video = { ...image, referenceKey: 'video', assetVersionId: '9007199254740995', mediaRole: 'reference_video', ordinal: 2 }
  const text = '@Image 1 @Video 1，@video 1。@Video 10 @Video 2 @Video 1abc @@Video 1 @Video 01'
  const state = EditorState.create({ schema, doc: schema.node('doc', null, [schema.node('paragraph', null, schema.text(text))]) })
  const before = bindNumberedMediaReferences(state.tr, [...refs, image])
  assert.match(before.doc.textContent, /@Video 1，/)
  const bound = bindNumberedMediaReferences(state.apply(before).tr, [...refs, image, video])
  const document = fromEditorDocument(bound.doc.toJSON(), [...refs, image, video])
  assert.deepEqual(json(document.content[0].content.filter(n => n.type === 'mention').map(n => n.referenceKey)), ['image', 'video', 'video'])
  assert.match(bound.doc.textContent, /@Video 10 @Video 2 @Video 1abc @@Video 1 @Video 01/)
  assert.equal(video.assetVersionId, '9007199254740995')
  const restored = toEditorDocument(document)
  assert.deepEqual(json(restored.content[0].content.filter(n => n.type === 'mention').map(n => n.attrs.label)), ['Image 1', 'Video 1', 'Video 1'])
})

test('删除首张素材后连续编号，重复提及同步更新且不改变元素名字和素材身份', () => {
  const images = ['a', 'b', 'c'].map((key, ordinal) => ({ referenceKey: key, assetVersionId: key, elementRevisionId: null, mediaRole: 'reference_image', ordinal }))
  const mentions = [['a', 'Image 1'], ['b', 'Image 2'], ['b', 'Image 2'], ['c', 'Image 3'], [refs[0].referenceKey, '女主角']]
  const doc = fromEditorDocument({ type: 'doc', content: [{ type: 'paragraph', content: mentions.map(([id, label]) => ({ type: 'mention', attrs: { id, label } })) }] }, [...images, ...refs])
  const next = toEditorDocument(removePromptReference(doc, [...images.slice(1), ...refs], 'a'))
  const result = next.content[0].content.filter(node => node.type === 'mention').map(node => [node.attrs.id, node.attrs.label])
  assert.equal(JSON.stringify(result), JSON.stringify([['b', 'Image 1'], ['b', 'Image 1'], ['c', 'Image 2'], [refs[0].referenceKey, '女主角']]))
  assert.equal(images[1].assetVersionId, 'b')
})
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
