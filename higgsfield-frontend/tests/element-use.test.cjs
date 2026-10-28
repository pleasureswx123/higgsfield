const { test } = require('node:test'),
  assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'),
  { join } = require('node:path'),
  { runInNewContext } = require('node:vm')
const ts = require('typescript'),
  vue = require('vue')
function load(file, mocks = {}) {
  const exports = {}
  runInNewContext(
    ts.transpileModule(readFileSync(join(__dirname, '../src', file + '.ts'), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    {
      exports,
      Error,
      AbortController,
      require(id) {
        if (id in mocks) return mocks[id]
        if (id === './draftReferences') return load('utils/draftReferences')
        if (id === './promptDocument') return load('utils/promptDocument')
        if (id === '@/utils/elementUse') return load('utils/elementUse')
        throw Error(id)
      },
    },
  )
  return exports
}
const candidate = {
  kind: 'element',
  id: '1',
  projectId: '99',
  displayName: '主角',
  allowedMediaRoles: ['reference_image', 'first_frame'],
  assetVersionIds: ['11', '12'],
  primaryAssetVersionId: '12',
  elementRevisionId: '20',
}
const prompt = () => ({
  schemaVersion: 1,
  type: 'doc',
  content: [
    { type: 'paragraph', content: [{ type: 'text', text: '保留原文', marks: [{ type: 'bold' }] }] },
  ],
})

test('Use 原子追加固定引用及可读标签，不覆盖原文并复用已有引用键', () => {
  const { prepareElementUse } = load('utils/elementUse'),
    original = prompt(),
    refs = []
  const result = prepareElementUse(original, refs, [candidate], null)
  assert.equal(original.content.length, 1)
  assert.equal(refs.length, 0)
  assert.equal(result.references.length, 1)
  assert.equal(result.references[0].elementRevisionId, '20')
  assert.equal(result.references[0].assetVersionId, '12')
  assert.equal(result.prompt.content[0].content[0].marks[0].type, 'bold')
  assert.equal(result.prompt.content[1].content[0].text, '@主角 ')
  const again = prepareElementUse(result.prompt, result.references, [candidate], null)
  assert.equal(again.references.length, 1)
  assert.equal(again.prompt.content.length, 2)
  const partial = prepareElementUse(original, [result.references[0]], [candidate], null)
  assert.equal(partial.references.length, 1)
  assert.equal(partial.references[0].referenceKey, result.references[0].referenceKey)
  const selected = [{ ...result.references[0], assetVersionId: '11' }]
  const preserved = prepareElementUse(original, selected, [candidate], null)
  assert.equal(preserved.references.length, 1)
  assert.equal(preserved.references[0].assetVersionId, '11')
})

test('Use 校验模型角色、图片总数与文档上限，失败不写入任何部分', () => {
  const { prepareElementUse } = load('utils/elementUse'),
    original = prompt()
  const model = {
    referenceRules: {
      maxTotal: 1,
      roles: { reference_image: { mediaTypes: ['image'], minCount: 0, maxCount: 1 } },
    },
  }
  assert.equal(prepareElementUse(original, [], [candidate], model).references.length, 1)
  assert.throws(() => prepareElementUse(original, [], [candidate, { ...candidate, elementRevisionId: '21' }], model), /总数限制/)
  assert.equal(original.content.length, 1)
  const first = prepareElementUse(original, [], [candidate], {
    referenceRules: {
      maxTotal: 1,
      roles: { first_frame: { mediaTypes: ['image'], minCount: 0, maxCount: 1 } },
    },
  })
  assert.equal(first.references[0].assetVersionId, '12')
  assert.throws(
    () => prepareElementUse(original, [], [{ ...candidate, assetVersionIds: [] }], null),
    /补图/,
  )
  assert.throws(
    () =>
      prepareElementUse(original, [], [candidate], { referenceRules: { maxTotal: 0, roles: {} } }),
    /不支持/,
  )
})
function setup() {
  const auth = vue.reactive({ token: 'one', user: { permissions: [] } }),
    calls = [],
    applied = [],
    hooks = {}
  const draft = { prompt: prompt(), references: [], model: null, kind: 'video' }
  const mod = load('composables/useElementUse', {
    vue: {
      ...vue,
      onActivated: (fn) => {
        hooks.activate = fn
      },
      onDeactivated: (fn) => {
        hooks.deactivate = fn
      },
      onBeforeUnmount: (fn) => {
        hooks.close = fn
      },
    },
    '@/stores/auth': { useAuthStore: () => auth },
    '@/api/references': {
      searchReferences: (...args) => new Promise((resolve) => calls.push({ args, resolve })),
    },
  })
  const scope = vue.effectScope(),
    state = scope.run(() =>
      mod.useElementUse(
        '99',
        () => draft,
        () => false,
        (value) => applied.push(value),
      ),
    )
  return {
    state,
    auth,
    calls,
    applied,
    draft,
    hooks,
    close() {
      hooks.close()
      scope.stop()
    },
  }
}
const item = { id: '1', name: '主角', projectId: '99', currentRevisionId: '20' }

test('Use 精确授权查询，保留模式；版本变更或草稿变化拒绝整批回填', async () => {
  const h = setup(),
    run = h.state.useElements([item])
  assert.equal(h.calls[0].args[0].elementId, '1')
  assert.equal(h.calls[0].args[0].kind, 'element')
  h.calls[0].resolve({ rows: [candidate] })
  assert.equal(await run, true)
  assert.equal(h.applied.length, 1)
  assert.equal(h.draft.kind, 'video')
  const stale = h.state.useElements([item])
  h.calls[1].resolve({ rows: [{ ...candidate, elementRevisionId: '21' }] })
  assert.equal(await stale, false)
  assert.equal(h.applied.length, 1)
  const changed = h.state.useElements([item])
  h.draft.prompt.content[0].content[0].text = '新输入'
  h.calls[2].resolve({ rows: [candidate] })
  assert.equal(await changed, false)
  assert.match(h.state.error.value, /已变化/)
  assert.equal(h.applied.length, 1)
  h.close()
})

test('Use 无媒体、跨项目和账号切换不回填，停用取消旧请求', async () => {
  const h = setup()
  assert.equal(await h.state.useElements([{ ...item, projectId: '100' }]), false)
  assert.equal(h.calls.length, 0)
  const missing = h.state.useElements([item])
  h.calls[0].resolve({ rows: [] })
  assert.equal(await missing, false)
  const run = h.state.useElements([item])
  h.auth.token = 'two'
  h.calls[1].resolve({ rows: [candidate] })
  assert.equal(await run, false)
  assert.equal(h.calls[1].args[1].aborted, true)
  const off = h.state.useElements([item])
  h.hooks.deactivate()
  h.calls[2].resolve({ rows: [candidate] })
  assert.equal(await off, false)
  assert.equal(h.applied.length, 0)
  h.close()
})

test('Use 按模型媒体类型选择角色，不将图片写入视频角色，失败保持原文和引用', () => {
  const { prepareElementUse } = load('utils/elementUse'),
    original = prompt(),
    refs = []
  const rules = {
    maxTotal: 5,
    roles: {
      reference_image: { mediaTypes: ['video'], minCount: 0, maxCount: 5 },
      first_frame: { mediaTypes: ['image'], minCount: 0, maxCount: 1 },
    },
  }
  const result = prepareElementUse(original, refs, [candidate], { referenceRules: rules })
  assert.equal(result.references.length, 1)
  assert.equal(result.references[0].mediaRole, 'first_frame')
  assert.equal(result.references[0].assetVersionId, '12')
  rules.roles.first_frame.mediaTypes = ['audio']
  assert.throws(
    () => prepareElementUse(original, refs, [candidate], { referenceRules: rules }),
    /不支持/,
  )
  assert.equal(refs.length, 0)
  assert.equal(original.content.length, 1)
  rules.roles.first_frame.mediaTypes = ['image']
  rules.roles.first_frame.maxCount = 0
  assert.throws(
    () => prepareElementUse(original, refs, [candidate], { referenceRules: rules }),
    /不支持/,
  )
})
