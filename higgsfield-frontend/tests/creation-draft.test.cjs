const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const { webcrypto } = require('node:crypto')
const ts = require('typescript')
const vue = require('vue')

function harness(api = {}, confirm = () => true, autoSave = false) {
  const folder = vue.ref(null)
  const auth = vue.reactive({ token: 'one', user: { permissions: [] } })
  const exported = {},
    calls = [],
    hooks = {}
  const source = readFileSync(
    require('node:path').join(__dirname, '../src/composables/useCreationDraft.ts'),
    'utf8',
  )
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const mocks = {
    '@/stores/auth': { useAuthStore: () => auth },
    '@/utils/promptDocument': promptHelpers(),
    '@/utils/modelTransition': transitionHelpers(),
    vue: {
      ...vue,
      onBeforeUnmount: (fn) => {
        hooks.unmount = fn
      },
      onActivated: (fn) => {
        hooks.activate = fn
      },
      onDeactivated: (fn) => {
        hooks.deactivate = fn
      },
    },
    'vue-router': {
      onBeforeRouteUpdate: (fn) => {
        hooks.update = fn
      },
      onBeforeRouteLeave: (fn) => {
        hooks.leave = fn
      },
    },
    '@/api/creation': {
      getModelCatalog: async () => ({ rows: [], total: 0 }),
      getCreationDrafts: async () => ({ rows: [], total: 0 }),
      saveCreationDraft: async (...args) => {
        calls.push(args)
        return {
          data: {
            id: '1',
            revision: String(calls.length),
            projectId: '9',
            kind: args[2],
            body: args[3],
          },
        }
      },
      ...api,
    },
  }
  runInNewContext(compiled, {
    exports: exported,
    require: (name) => mocks[name],
    crypto: webcrypto,
    AbortController,
    setTimeout, clearTimeout,
    window: { confirm, addEventListener() {}, removeEventListener() {} },
  })
  const state = exported.useCreationDraft('9', () => folder.value, { autoSave })
  state.formRef.value = { validate: async () => true }
  return { state, auth, calls, hooks, folder }
}

test('保存后重置脏状态，后续编辑更新同一草稿且保留精确参数类型', async () => {
  const { state, calls } = harness()
  assert.equal(state.dirty.value, false)
  state.prompt.value = '测试提示词'
  assert.equal(state.dirty.value, true)
  await state.save()
  assert.equal(state.dirty.value, false)
  state.setParameter('audio', false)
  state.setParameter('seed', 0)
  await state.save()
  assert.equal(calls[1][0].id, '1')
  assert.equal(calls[1][3].parameters.audio, false)
  assert.equal(calls[1][3].parameters.seed, 0)
  state.setParameter('seed', undefined)
  assert.equal('seed' in state.parameters.value, false)
})

test('未知结果重试冻结请求和幂等键，即使外部输入变化也不另建草稿', async () => {
  const attempts = []
  const { state } = harness({
    saveCreationDraft: async (...args) => {
      attempts.push(args)
      throw new Error('离线')
    },
  })
  state.prompt.value = '保留输入'
  await state.save()
  await state.save()
  assert.equal(attempts[0][4], attempts[1][4])
  assert.equal(state.prompt.value, '保留输入')
  assert.equal(state.dirty.value, true)
  state.prompt.value = '新的输入'
  await state.save()
  assert.equal(attempts[1][4], attempts[2][4])
  assert.equal(JSON.stringify(attempts[0]), JSON.stringify(attempts[2]))
  assert.equal(state.locked.value, true)
})

test('长提示词按后端节点上限分段，不截断换行或Unicode字符', async () => {
  const { state, calls } = harness()
  state.prompt.value = '文'.repeat(21000) + '\n' + '😀'.repeat(2000)
  await state.save()
  const nodes = calls[0][3].prompt.content[0].content
  assert.equal(nodes.map((node) => node.text).join(''), state.prompt.value)
  assert.ok(nodes.every((node) => [...node.text].length <= 20000))
})

test('重新打开再保存完整保留富文本、引用与回填上下文', async () => {
  const full = {
    id: '8',
    projectId: '9',
    kind: 'image',
    revision: '4',
    updateTime: '2026-10-27T00:00:00Z',
    body: {
      schemaVersion: 1,
      modelVersionId: '7',
      parameters: { seed: 0 },
      folderId: '3',
      targetElementId: '4',
      sourceJobId: '9007199254740993',
      returnContext: { route: 'project-elements', projectId: '9', elementId: '4' },
      prompt: {
        schemaVersion: 1,
        type: 'doc',
        content: [
          {
            type: 'paragraph',
            content: [
              { type: 'text', text: '带格式', marks: [{ type: 'bold' }] },
              { type: 'mention', referenceKey: '2' },
            ],
          },
        ],
      },
    },
    references: [
      {
        referenceKey: '2',
        assetVersionId: '5',
        elementRevisionId: '6',
        mediaRole: 'reference_image',
        ordinal: 0,
      },
    ],
  }
  const { state, calls } = harness({ getCreationDraft: async () => ({ data: full }) })
  await state.openDraft('8')
  assert.equal(state.richPrompt.value, true)
  assert.equal(state.missingModel.value, true)
  assert.equal(state.dirty.value, false)
  await state.save()
  const savedBody = JSON.parse(JSON.stringify(calls[0][3]))
  assert.deepEqual(savedBody, full.body)
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][5])), full.references)
  assert.equal(calls[0][0].revision, '4')
})

test('跨项目详情拒绝打开，读取失败保留当前提示词', async () => {
  const { state } = harness({
    getCreationDraft: async () => ({ data: { projectId: 'other-project' } }),
  })
  state.prompt.value = '本地未保存内容'
  await state.openDraft('8')
  assert.equal(state.prompt.value, '本地未保存内容')
  assert.equal(state.draft.value, null)
  assert.equal(state.opening.value, false)
  assert.match(state.error.value, /不属于当前项目/)
})

function transitionHelpers() {
  const source = readFileSync(require('node:path').join(__dirname, '../src/utils/modelTransition.ts'), 'utf8')
  const exported = {}
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  runInNewContext(compiled, { exports: exported })
  return exported
}

function referenceHelpers() {
  const source = readFileSync(
    require('node:path').join(__dirname, '../src/utils/draftReferences.ts'),
    'utf8',
  )
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const exported = {}
  runInNewContext(compiled, { exports: exported })
  return exported
}

function promptHelpers() {
  const source = readFileSync(
    require('node:path').join(__dirname, '../src/utils/promptDocument.ts'),
    'utf8',
  )
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const exported = {}
  runInNewContext(compiled, { exports: exported })
  return exported
}

test('提及插入与移除更新保护键，保存保留原文本格式和固定引用', async () => {
  const { insertPromptNode, editPrompt } = promptHelpers()
  const { state, calls } = harness()
  state.references.value = [
    {
      referenceKey: '12',
      assetVersionId: '99',
      elementRevisionId: null,
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
        content: [{ type: 'text', text: '普通 @ 文本', marks: [{ type: 'bold' }] }],
      },
    ],
  }
  state.promptDocument.value = insertPromptNode(original, 0, 0, {
    type: 'mention',
    referenceKey: '12',
  })
  assert.equal(state.protectedReferenceKeys.value[0], '12')
  assert.equal(original.content[0].content.length, 1)
  await state.save()
  assert.equal(calls[0][3].prompt.content[0].content[0].marks[0].type, 'bold')
  assert.equal(calls[0][3].prompt.content[0].content[1].referenceKey, '12')
  assert.equal(calls[0][5][0].assetVersionId, '99')
  state.promptDocument.value = editPrompt(state.promptDocument.value, (body) =>
    body.content[0].content.splice(1, 1),
  )
  assert.equal(state.protectedReferenceKeys.value.length, 0)
  assert.equal(state.prompt.value, '普通 @ 文本')
  assert.equal(state.dirty.value, true)
})

test('提示词编辑超限时不修改原文档', () => {
  const { editPrompt, insertPromptNode } = promptHelpers()
  const original = {
    schemaVersion: 1,
    type: 'doc',
    content: [{ type: 'paragraph', content: [{ type: 'text', text: '保留' }] }],
  }
  assert.throws(
    () =>
      editPrompt(original, (body) => {
        body.content[0].content[0].text = '文'.repeat(20001)
      }),
    /20000/,
  )
  assert.equal(original.content[0].content[0].text, '保留')
  const full = {
    ...original,
    content: [
      {
        type: 'paragraph',
        content: Array.from({ length: 100 }, () => ({ type: 'text', text: '' })),
      },
    ],
  }
  assert.throws(() => insertPromptNode(full, 0, 99, { type: 'mention', referenceKey: '1' }), /100/)
  assert.equal(full.content[0].content.length, 100)
})

test('元素引用固定全部版本与修订，首帧仅选主图，编号不丢失bigint精度', () => {
  const { appendCandidate } = referenceHelpers()
  const original = [
    {
      referenceKey: '9007199254740993',
      assetVersionId: '10',
      elementRevisionId: null,
      mediaRole: 'reference_image',
      ordinal: 0,
    },
  ]
  const candidate = {
    kind: 'element',
    id: '2',
    projectId: '9',
    displayName: '角色',
    allowedMediaRoles: ['reference_image', 'first_frame'],
    assetVersionIds: ['11', '12'],
    primaryAssetVersionId: '12',
    elementRevisionId: '20',
  }
  const result = appendCandidate(original, candidate, 'reference_image')
  assert.equal(result.length, 3)
  assert.equal(result[1].referenceKey, '9007199254740994')
  assert.equal(result[2].referenceKey, result[1].referenceKey)
  assert.equal(result[1].elementRevisionId, '20')
  assert.equal(original.length, 1)
  const first = appendCandidate([], candidate, 'first_frame')
  assert.equal(first.length, 1)
  assert.equal(first[0].assetVersionId, '12')
  assert.throws(() => appendCandidate(result, candidate, 'reference_image'), /已经加入/)
  assert.throws(() => appendCandidate([], candidate, 'reference_video'), /不支持/)
})

test('引用排序不改变固定版本或稳定键，数量上限不截断元素图片', () => {
  const { appendCandidate, moveReference } = referenceHelpers()
  const original = [
    {
      referenceKey: '1',
      assetVersionId: '10',
      elementRevisionId: null,
      mediaRole: 'reference_image',
      ordinal: 0,
    },
    {
      referenceKey: '2',
      assetVersionId: '20',
      elementRevisionId: null,
      mediaRole: 'reference_image',
      ordinal: 1,
    },
  ]
  const moved = moveReference(original, 1, -1)
  assert.equal(moved[0].assetVersionId, '20')
  assert.equal(moved[0].referenceKey, '2')
  assert.equal(moved[0].ordinal, 0)
  assert.equal(original[0].assetVersionId, '10')
  const full = Array.from({ length: 200 }, (_, ordinal) => ({
    ...original[0],
    referenceKey: String(ordinal + 1),
    ordinal,
  }))
  assert.throws(
    () =>
      appendCandidate(
        full,
        {
          allowedMediaRoles: ['reference_image'],
          assetVersionIds: ['999'],
          elementRevisionId: '3',
        },
        'reference_image',
      ),
    /最多保存200/,
  )
})

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('账号切换隔离迟到的草稿读取与保存结果', async () => {
  const read = deferred(),
    write = deferred()
  const { state, auth } = harness({
    getCreationDraft: () => read.promise,
    saveCreationDraft: () => write.promise,
  })
  const opening = state.openDraft('8')
  auth.token = 'two'
  read.resolve({ data: { projectId: '9', body: {} } })
  await opening
  assert.equal(state.draft.value, null)
  assert.equal(state.opening.value, false)
  state.prompt.value = '第二个账号'
  const saving = state.save()
  await Promise.resolve()
  await Promise.resolve()
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.saving.value, true)
  auth.token = 'three'
  write.resolve({ data: { id: '8' } })
  await saving
  assert.equal(state.draft.value, null)
  assert.equal(state.prompt.value, '')
  assert.equal(state.notice.value, '')
  assert.equal(state.dirty.value, false)
})

test('表单校验期间账号切换或页面停用不发送保存，恢复保留本地输入', async () => {
  for (const action of ['account', 'deactivate']) {
    const validation = deferred()
    const { state, auth, hooks, calls } = harness()
    state.prompt.value = '未提交内容'
    state.formRef.value = { validate: () => validation.promise }
    const saving = state.save()
    if (action === 'account') auth.token = 'two'
    else hooks.deactivate()
    validation.resolve(true)
    await saving
    assert.equal(calls.length, 0)
    if (action === 'deactivate') {
      hooks.activate()
      assert.equal(state.prompt.value, '未提交内容')
      assert.equal(state.dirty.value, true)
    }
  }
})

test('缓存停用后迟到的模型和草稿列表不会恢复，激活重新读取', async () => {
  const catalog = deferred(),
    drafts = deferred()
  let reads = 0
  const { state, hooks } = harness({
    getModelCatalog: () => {
      reads++
      return reads === 1 ? catalog.promise : Promise.resolve({ rows: [], total: 0 })
    },
    getCreationDrafts: () => drafts.promise,
  })
  hooks.deactivate()
  catalog.resolve({ rows: [{ versionId: 'old' }], total: 1 })
  drafts.resolve({ rows: [{ id: 'old' }], total: 1 })
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(state.models.value.length, 0)
  assert.equal(state.drafts.value.length, 0)
  hooks.activate()
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(reads, 2)
})

test('草稿超时后缓存恢复重试原请求，成功后使用已返回草稿更新且保留新输入', async () => {
  const attempts = []
  const { state, hooks } = harness({
    saveCreationDraft: async (...args) => {
      attempts.push(args)
      if (attempts.length === 1) throw Object.assign(new Error('超时'), { code: 408 })
      return {
        data: {
          id: '88',
          revision: String(attempts.length),
          projectId: '9',
          body: args[3],
          references: args[5],
        },
      }
    },
  })
  state.prompt.value = '原请求'
  state.references.value = [
    {
      referenceKey: '1',
      assetVersionId: '10',
      elementRevisionId: null,
      mediaRole: 'reference_image',
      ordinal: 0,
    },
  ]
  await state.save()
  assert.equal(state.uncertain.value, true)
  assert.equal(hooks.leave(), false)
  assert.equal(hooks.update(
    { path: '/projects/10', fullPath: '/projects/10', params: { id: '10' } },
    { path: '/projects/9', fullPath: '/projects/9', params: { id: '9' } },
  ), false)
  state.newDraft()
  state.changeKind('video')
  state.setParameter('seed', 2)
  assert.equal(state.kind.value, 'image')
  assert.equal(state.parameters.value.seed, undefined)
  hooks.deactivate()
  await state.save()
  assert.equal(attempts.length, 1)
  hooks.activate()
  state.prompt.value = '外部新输入'
  state.references.value[0].assetVersionId = '11'
  state.formRef.value = { validate: async () => false }
  await state.save()
  assert.equal(JSON.stringify(attempts[0]), JSON.stringify(attempts[1]))
  assert.equal(state.draft.value.id, '88')
  assert.equal(state.locked.value, false)
  assert.equal(state.dirty.value, true)
  assert.equal(state.prompt.value, '外部新输入')
  state.formRef.value = { validate: async () => true }
  await state.save()
  assert.equal(attempts[2][0].id, '88')
  assert.equal(attempts[2][0].revision, '2')
  assert.notEqual(attempts[2][4], attempts[1][4])
  assert.equal(attempts[2][5][0].assetVersionId, '11')
})

test('处理中响应保留草稿请求，明确拒绝释放锁且下一次保存使用新键', async () => {
  const attempts = []
  const { state } = harness({
    saveCreationDraft: async (...args) => {
      attempts.push(args)
      throw Object.assign(new Error('拒绝'), {
        code: 601,
        errorCode: attempts.length === 1 ? 'IDEMPOTENCY_IN_PROGRESS' : 'VALIDATION_ERROR',
      })
    },
  })
  state.prompt.value = '内容'
  await state.save()
  assert.equal(state.uncertain.value, true)
  await state.save()
  assert.equal(attempts[0][4], attempts[1][4])
  assert.equal(state.locked.value, false)
  state.prompt.value = '修正内容'
  await state.save()
  assert.notEqual(attempts[1][4], attempts[2][4])
})

test('手动引用按模型过滤媒体类型，按实际新增版本计数，超限整批拒绝', () => {
  const { appendCandidate, compatibleReferenceRoles } = referenceHelpers()
  const candidate = {
    kind: 'element',
    id: '2',
    projectId: '9',
    displayName: '角色',
    allowedMediaRoles: ['reference_image', 'first_frame'],
    assetVersionIds: ['11', '12'],
    primaryAssetVersionId: '12',
    elementRevisionId: '20',
  }
  const model = {
    referenceRules: {
      maxTotal: 2,
      roles: {
        reference_image: { mediaTypes: ['image'], minCount: 0, maxCount: 1 },
        first_frame: { mediaTypes: ['image'], minCount: 0, maxCount: 1 },
        reference_video: { mediaTypes: ['video'], minCount: 0, maxCount: 1 },
      },
    },
  }
  const original = []
  assert.throws(
    () => appendCandidate(original, candidate, 'reference_image', model),
    /角色的数量限制/,
  )
  assert.equal(original.length, 0)
  const first = appendCandidate(original, candidate, 'first_frame', model)
  assert.equal(first.length, 1)
  assert.equal(first[0].assetVersionId, '12')
  model.referenceRules.roles.reference_image.maxCount = 2
  assert.throws(() => appendCandidate(first, candidate, 'reference_image', model), /总数限制/)
  assert.equal(first.length, 1)
  const partial = appendCandidate([], candidate, 'reference_image')
  assert.equal(appendCandidate([partial[0]], candidate, 'reference_image', model).length, 2)
  model.referenceRules.roles.reference_image.mediaTypes = ['video']
  assert.equal(compatibleReferenceRoles(candidate, model).join(','), 'first_frame')
  assert.throws(() => appendCandidate([], candidate, 'reference_image', model), /不支持/)
  const video = {
    ...candidate,
    kind: 'asset',
    elementRevisionId: undefined,
    allowedMediaRoles: ['reference_video'],
    assetVersionIds: ['99'],
  }
  assert.equal(appendCandidate([], video, 'reference_video', model)[0].assetVersionId, '99')
})

test('空白新草稿跟随目录，已有输入及已保存草稿保持发起目录，新建重新取当前目录',async()=>{
 const {state,folder,calls}=harness()
 folder.value='9007199254740993';assert.equal(state.body.value.folderId,folder.value);assert.equal(state.dirty.value,false)
 state.prompt.value='目录内创作';folder.value='7'
 assert.equal(state.body.value.folderId,'9007199254740993')
 await state.save();assert.equal(calls[0][3].folderId,'9007199254740993')
 folder.value='8';assert.equal(state.body.value.folderId,'9007199254740993')
 state.newDraft();assert.equal(state.body.value.folderId,'8');assert.equal(state.dirty.value,false)
 folder.value=null;assert.equal(state.body.value.folderId,null);assert.equal(state.dirty.value,false)
})

test('草稿保存结果未知时目录变化不改写重试原请求',async()=>{
 const attempts=[]
 const {state,folder}=harness({saveCreationDraft:async(...args)=>{attempts.push(args);throw new Error('断网')}})
 folder.value='17';state.prompt.value='原目录草稿';await state.save()
 folder.value='18';await state.save()
 assert.equal(attempts[0][3].folderId,'17');assert.equal(attempts[1][3].folderId,'17')
 assert.equal(attempts[0][4],attempts[1][4]);assert.equal(state.body.value.folderId,'17')
})

test('同项目目录导航保留草稿并免确认，跨项目和离开仍受保护', async () => {
  let confirmations = 0
  const { state, folder, hooks } = harness({}, () => { confirmations++; return false })
  folder.value = '17'
  state.prompt.value = '保留原目录输入'
  const from = { path: '/projects/9', fullPath: '/projects/9?folder=17', params: { id: '9' } }
  const to = { ...from, fullPath: '/projects/9?folder=18' }
  assert.equal(hooks.update(to, from), true)
  folder.value = '18'
  assert.equal(confirmations, 0)
  assert.equal(state.prompt.value, '保留原目录输入')
  assert.equal(state.body.value.folderId, '17')
  assert.equal(hooks.update({ path: '/projects/10', fullPath: '/projects/10', params: { id: '10' } }, from), false)
  assert.equal(hooks.leave(), false)
  assert.equal(confirmations, 2)
})

test('未确认保存允许同项目导航，仍锁定原请求并禁止离开项目', async () => {
  const attempts = []
  const { state, folder, hooks } = harness({ saveCreationDraft: async (...args) => {
    attempts.push(args)
    throw new Error('连接中断')
  } })
  folder.value = '17'
  state.prompt.value = '未知结果'
  await state.save()
  const from = { path: '/projects/9', fullPath: '/projects/9?folder=17', params: { id: '9' } }
  assert.equal(hooks.update({ ...from, fullPath: '/projects/9?folder=18' }, from), true)
  folder.value = '18'
  assert.equal(hooks.leave(), false)
  await state.save()
  assert.equal(attempts[0][4], attempts[1][4])
  assert.equal(attempts[1][3].folderId, '17')
  assert.equal(state.locked.value, true)
})

test('切换模型比较参数与引用，取消无损、确认保留兼容值，切回恢复原参数', async () => {
  let allow = false
  const messages = []
  const { state } = harness({}, (message) => { messages.push(message); return allow })
  await Promise.resolve()
  const a = {
    versionId: '1', defaultParameters: { seed: 3, audio: true },
    parametersSchema: { properties: { seed: { type: 'integer' }, audio: { type: 'boolean' } }, required: [] },
    referenceRules: { maxTotal: 2, roles: { reference_image: { mediaTypes: ['image'], minCount: 0, maxCount: 2 } } },
  }
  const b = { ...a, versionId: '2', defaultParameters: { seed: 5 },
    parametersSchema: { properties: { seed: { type: 'integer' } }, required: [] },
    referenceRules: { maxTotal: 0, roles: {} },
  }
  state.models.value = [a, b]
  state.choose('1')
  state.setParameter('seed', 0)
  state.setParameter('audio', false)
  state.prompt.value = '原始提示词'
  state.references.value = [{ referenceKey: '1', assetVersionId: '99', elementRevisionId: null, mediaRole: 'reference_image', ordinal: 0 }]
  state.choose('2')
  assert.equal(state.selected.value.versionId, '1')
  assert.equal(state.parameters.value.audio, false)
  assert.match(messages[0], /audio/)
  assert.match(messages[0], /reference_image/)
  allow = true
  state.choose('2')
  assert.equal(state.parameters.value.seed, 0)
  assert.equal('audio' in state.parameters.value, false)
  assert.equal(state.references.value[0].assetVersionId, '99')
  assert.equal(state.prompt.value, '原始提示词')
  state.setParameter('seed', 8)
  state.choose('1')
  assert.equal(state.parameters.value.seed, 0)
  assert.equal(state.parameters.value.audio, false)
  state.newDraft()
  state.choose('1')
  assert.equal(state.parameters.value.seed, 3)
  assert.equal(state.parameters.value.audio, true)
})

test('目标参数遵循类型、枚举、数值范围和Unicode长度，不转换真假值或数字字符串', () => {
  const { modelTransition } = transitionHelpers()
  const model = { defaultParameters: { count: 1 }, parametersSchema: { properties: {
    count: { type: 'integer', minimum: 1, maximum: 4 },
    quality: { type: 'string', enum: ['high'] },
    audio: { type: 'boolean' },
    label: { type: 'string', minLength: 1, maxLength: 1 },
    seed: { type: 'integer' },
  } }, referenceRules: { maxTotal: 0, roles: {} } }
  const result = modelTransition(model, { count: 2.5, quality: 'low', audio: 'false', label: '😀', seed: 0 }, [])
  assert.equal(result.parameters.count, 1)
  assert.equal(result.parameters.label, '😀')
  assert.equal(result.parameters.seed, 0)
  assert.equal('audio' in result.parameters, false)
  assert.equal('quality' in result.parameters, false)
  assert.match(result.warnings.join(''), /count、quality、audio/)
})

test('空白创作跟随目录，已输入内容不会被移动到另一目录', async () => {
  const { state, folder } = harness()
  folder.value = '20'
  await vue.nextTick()
  assert.equal(state.body.value.folderId, '20')
  assert.equal(state.dirty.value, false)
  state.prompt.value = '当前目录的创作'
  folder.value = '21'
  await vue.nextTick()
  assert.equal(state.body.value.folderId, '20')
  assert.equal(state.dirty.value, true)
})


test('图片视频无确认往返切换，各自保留输入、参数、引用和保存身份', async () => {
  let confirmations = 0
  const { state, calls } = harness({}, () => { confirmations++; return false })
  state.prompt.value = '图片描述'
  state.setParameter('quality', 'high')
  state.references.value = [{ referenceKey: 'image-ref', assetVersionId: '8', elementRevisionId: null, mediaRole: 'reference_image', ordinal: 0 }]
  await state.save()
  const imageId = state.draft.value.id
  state.changeKind('video')
  assert.equal(state.kind.value, 'video')
  assert.equal(state.prompt.value, '')
  assert.equal(state.references.value.length, 0)
  state.prompt.value = '视频描述'
  state.setParameter('duration', 12)
  state.changeKind('image')
  assert.equal(state.prompt.value, '图片描述')
  assert.equal(state.parameters.value.quality, 'high')
  assert.equal(state.references.value[0].assetVersionId, '8')
  assert.equal(state.draft.value.id, imageId)
  assert.equal(state.dirty.value, true, '另一类型未保存输入仍受到离开保护')
  state.changeKind('video')
  assert.equal(state.prompt.value, '视频描述')
  assert.equal(state.parameters.value.duration, 12)
  assert.equal(state.draft.value, null)
  await state.save()
  assert.equal(calls[1][0], null)
  assert.equal(calls[1][2], 'video')
  assert.equal(state.dirty.value, false)
  assert.equal(confirmations, 0)
})

test('切换账号清除两种类型缓存，不能恢复上个账号内容', () => {
  const { state, auth } = harness()
  state.prompt.value = '旧账号图片'
  state.changeKind('video')
  state.prompt.value = '旧账号视频'
  auth.token = 'new-account'
  assert.equal(state.prompt.value, '')
  state.changeKind('video')
  assert.equal(state.prompt.value, '')
  assert.equal(state.dirty.value, false)
})


test('自动保存同时处理切换前后的两种草稿，不串内容', async () => {
  const { state, calls, hooks } = harness({}, () => true, true)
  state.prompt.value = '图片自动保存'
  state.changeKind('video')
  state.prompt.value = '视频自动保存'
  await new Promise(resolve => setTimeout(resolve, 2100))
  assert.equal(calls.length, 2)
  assert.deepEqual(calls.map(call => call[2]).sort(), ['image', 'video'])
  assert.equal(state.dirty.value, false)
  state.changeKind('image')
  assert.equal(state.prompt.value, '图片自动保存')
  assert.ok(state.draft.value)
  hooks.unmount()
})

test('自动保存失败停止循环，手动重试复用原幂等键', async () => {
  const attempts = []
  const { state, hooks } = harness({ saveCreationDraft: async (...args) => {
    attempts.push(args)
    if (attempts.length === 1) throw new Error('网络断开')
    return { data: { id: '8', revision: '1', kind: args[2], body: args[3] } }
  } }, () => true, true)
  state.prompt.value = '保留我'
  await new Promise(resolve => setTimeout(resolve, 2100))
  assert.equal(attempts.length, 1)
  assert.ok(state.autoSaveError.value)
  await state.save(true)
  assert.equal(attempts[0][4], attempts[1][4])
  assert.equal(state.dirty.value, false)
  hooks.unmount()
})
