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
const { insertElementMention, prepareMentionBatch } = load('promptMention')
const candidate = {
  kind: 'element',
  id: '1',
  projectId: '2',
  displayName: '主角',
  elementRevisionId: '20',
  assetVersionIds: ['12'],
  allowedMediaRoles: ['reference_image'],
}
const doc = () => ({
  schemaVersion: 1,
  type: 'doc',
  content: [
    {
      type: 'paragraph',
      content: [{ type: 'text', text: '前景 @1 后景', marks: [{ type: 'bold' }] }],
    },
  ],
})
const cursor = { block: 0, index: 0, start: 3, end: 5 }
test('光标位置替换保留前后文字及标记，并固定元素和素材版本', () => {
  const original = doc(),
    result = insertElementMention(original, [], candidate, null, cursor)
  const nodes = result.prompt.content[0].content
  assert.equal(nodes[0].text, '前景 @主角 ')
  assert.equal(nodes[1].type, 'mention')
  assert.equal(nodes[2].text, ' 后景')
  assert.equal(nodes[2].marks[0].type, 'bold')
  assert.equal(result.references[0].assetVersionId, '12')
  assert.equal(result.references[0].elementRevisionId, '20')
  assert.equal(original.content[0].content.length, 1)
  const restored = JSON.parse(JSON.stringify(result))
  assert.equal(
    restored.prompt.content[0].content[1].referenceKey,
    restored.references[0].referenceKey,
  )
})
test('同名不同元素不混淆，同版本再次提及复用引用键', () => {
  const first = insertElementMention(doc(), [], candidate, null, cursor)
  const again = insertElementMention(doc(), first.references, candidate, null, cursor)
  assert.equal(again.references.length, 1)
  const other = insertElementMention(
    doc(),
    first.references,
    { ...candidate, id: '2', elementRevisionId: '21', assetVersionIds: ['13'] },
    null,
    cursor,
  )
  assert.equal(other.references.length, 2)
  assert.notEqual(other.references[0].referenceKey, other.references[1].referenceKey)
})
test('模型不兼容、超出数量或光标失效均不修改原数据', () => {
  const original = doc(),
    refs = []
  assert.throws(
    () =>
      insertElementMention(
        original,
        refs,
        candidate,
        { referenceRules: { maxTotal: 0, roles: {} } },
        cursor,
      ),
    /不支持/,
  )
  assert.throws(
    () =>
      insertElementMention(
        original,
        refs,
        candidate,
        {
          referenceRules: {
            maxTotal: 0,
            roles: { reference_image: { maxCount: 1, mediaTypes: ['image'] } },
          },
        },
        cursor,
      ),
    /总数/,
  )
  assert.throws(
    () => insertElementMention(original, refs, candidate, null, { ...cursor, end: 999 }),
    /位置/,
  )
  assert.equal(refs.length, 0)
  assert.equal(original.content[0].content[0].text, '前景 @1 后景')
})

test('已有主图后追加附图保持同一引用键，数量限制仍生效', () => {
  const first = insertElementMention(doc(), [], candidate, null, cursor)
  const result = insertElementMention(
    doc(),
    first.references,
    { ...candidate, assetVersionIds: ['12', '13'] },
    null,
    cursor,
  )
  assert.equal(result.references.length, 2)
  assert.equal(result.references[0].referenceKey, result.references[1].referenceKey)
  assert.equal(first.references.length, 1)
})

test('一次粘贴不同元素保留各自版本和独立引用键，重复提及复用同键', () => {
  const woman = { ...candidate, id: '2', displayName: 'woman', elementRevisionId: '21', assetVersionIds: ['13'] }
  const original = []
  const batch = prepareMentionBatch(original, [candidate, woman, candidate], null)
  assert.equal(batch.references.length, 2)
  assert.notEqual(batch.keys[0], batch.keys[1])
  assert.equal(batch.keys[0], batch.keys[2])
  assert.equal(batch.references.find(item => item.referenceKey === batch.keys[0]).assetVersionId, '12')
  assert.equal(batch.references.find(item => item.referenceKey === batch.keys[1]).assetVersionId, '13')
  assert.equal(original.length, 0)
})
test('批量引用中无效元素使整批失败，原引用不被部分修改', () => {
  const original = []
  assert.throws(() => prepareMentionBatch(original, [candidate, { ...candidate, elementRevisionId: undefined }], null))
  assert.equal(original.length, 0)
})
