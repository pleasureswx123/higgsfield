const { test } = require('node:test'),
  assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'),
  { join } = require('node:path'),
  { runInNewContext } = require('node:vm')
const { webcrypto } = require('node:crypto'),
  ts = require('typescript'),
  vue = require('vue')
function setup(api = {}) {
  const exports = {},
    calls = [],
    routes = [],
    hooks = {},
    auth = vue.reactive({ token: 'one', user: { user: { userId: 1 }, permissions: [] } })
  const task = vue.ref({
    id: '9007199254740993',
    projectId: '7',
    kind: 'image',
    allowedActions: ['generation:copy-input'],
  })
  const input = {
    prompt: {
      schemaVersion: 1,
      type: 'doc',
      content: [
        {
          type: 'paragraph',
          content: [
            { type: 'text', text: '原始输入', marks: [{ type: 'bold' }] },
            { type: 'mention', referenceKey: '2' },
          ],
        },
      ],
    },
    parameters: { seed: 0, enabled: false },
    references: [
      {
        referenceKey: '2',
        assetVersionId: '9007199254740995',
        ordinal: 0,
        elementRevisionId: null,
        mediaRole: 'reference_image',
      },
    ],
    modelVersionId: '9',
  }
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/useGenerationCopy.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS } },
    ).outputText,
    {
      exports,
      Error,
      AbortController,
      crypto: webcrypto,
      require(id) {
        if (id === 'vue')
          return {
            ...vue,
            onActivated: (fn) => (hooks.activate = fn),
            onDeactivated: (fn) => (hooks.deactivate = fn),
            onBeforeUnmount: (fn) => (hooks.close = fn),
          }
        if (id === 'vue-router')
          return {
            useRouter: () => ({
              push: async (route) => {
                routes.push(route)
                return api.push?.(route)
              },
            }),
          }
        if (id.includes('stores/auth')) return { useAuthStore: () => auth }
        if (id.includes('api/generations'))
          return {
            getGenerationInput: async (...args) => (api.read ? api.read(...args) : { data: input }),
          }
        return {
          saveCreationDraft: async (...args) => {
            calls.push(args)
            return api.save ? api.save(...args) : { data: { id: '11' } }
          },
        }
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() => exports.useGenerationCopy(() => task.value))
  return {
    state,
    task,
    input,
    calls,
    routes,
    hooks,
    auth,
    close() {
      hooks.close()
      scope.stop()
    },
  }
}
test('复制完整输入及字符串来源编号，只保存草稿并导航，不提交生成', async () => {
  const h = setup()
  assert.equal(await h.state.copy(), true)
  const args = h.calls[0]
  assert.equal(args[0], null)
  assert.equal(args[1], '7')
  assert.equal(args[2], 'image')
  assert.deepEqual(JSON.parse(JSON.stringify(args[3].prompt)), h.input.prompt)
  assert.equal(args[3].sourceJobId, '9007199254740993')
  assert.equal(args[3].parameters.seed, 0)
  assert.equal(args[3].parameters.enabled, false)
  assert.equal(args[5][0].assetVersionId, '9007199254740995')
  assert.equal(h.routes[0].query.draft, '11')
  h.close()
})
test('保存结果未知重用固定请求和幂等键，导航被拒后只重试打开', async () => {
  let writes = 0,
    navigation = 0
  const h = setup({
    save: async () => {
      if (++writes === 1) throw new Error('连接中断')
      return { data: { id: '11' } }
    },
    push: () => (++navigation === 1 ? {} : undefined),
  })
  await h.state.copy()
  assert.equal(h.state.retryable.value, true)
  h.input.parameters.seed = 99
  await h.state.copy()
  assert.equal(h.calls[1][4], h.calls[0][4])
  assert.equal(h.calls[1][3].parameters.seed, 0)
  assert.equal(h.state.retryable.value, true)
  assert.equal(await h.state.copy(), true)
  assert.equal(writes, 2)
  h.close()
})
test('权限或任务切换时丢弃晚到读取，不保存旧任务输入', async () => {
  let resolve
  const h = setup({ read: () => new Promise((done) => (resolve = done)) })
  const pending = h.state.copy()
  h.auth.token = 'two'
  resolve({ data: h.input })
  await pending
  assert.equal(h.calls.length, 0)
  assert.equal(h.routes.length, 0)
  h.task.value.allowedActions = []
  await h.state.copy()
  assert.equal(h.calls.length, 0)
  h.close()
})
test('不可编辑参数明确报错而非静默丢失，业务拒绝后允许重新读取', async () => {
  const h = setup()
  h.input.parameters.unsupported = { value: 1 }
  await h.state.copy()
  assert.equal(h.calls.length, 0)
  assert.match(h.state.error.value, /不支持/)
  h.close()
  const denied = setup({
    save: async () => {
      throw Object.assign(new Error('模型不可用'), { code: 601 })
    },
  })
  await denied.state.copy()
  assert.equal(denied.state.retryable.value, false)
  assert.equal(denied.routes.length, 0)
  denied.close()
})
