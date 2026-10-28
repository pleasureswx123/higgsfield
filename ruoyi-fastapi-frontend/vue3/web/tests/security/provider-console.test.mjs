import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'

const connection = (id) => ({
  id,
  name: `连接${id}`,
  environment: 'test',
  status: 'draft',
  revision: '3',
  currentVersion: {
    id: '10',
    versionNo: 1,
    baseUrl: 'https://example.com/',
    adapterVersion: 'test-v1',
    config: {
      allowedHosts: ['example.com'],
      bizId: 'op',
      connectTimeoutSeconds: 10,
      readTimeoutSeconds: 60,
      operationTimeoutSeconds: 120,
      taskTimeoutSeconds: 3600,
    },
  },
})

async function harness(overrides = {}) {
  const user = reactive({ permissions: ['provider:write'] })
  const saved = [],
    hooks = {}
  const api = {
    listProviderConnections: async () => ({ rows: [], total: 0 }),
    getProviderConnection: async (id) => ({ data: connection(id) }),
    listProviderAccounts: async () => ({ rows: [], total: 0 }),
    saveProviderConnection: async (...args) => {
      saved.push(args)
      return { data: connection('1') }
    },
    createProviderAccount: async (...args) => {
      saved.push(args)
      return {}
    },
    ...overrides,
  }
  const context = createContext({ crypto: webcrypto, window: { confirm: () => true, removeEventListener: () => {} } })
  const mocks = {
    vue: {
      computed,
      reactive,
      ref,
      onBeforeUnmount: (fn) => {
        hooks.unmount = fn
      },
      onMounted: (fn) => {
        hooks.mount = fn
      },
    },
    'vue-router': {
      onBeforeRouteLeave: (fn) => {
        hooks.leave = fn
      },
    },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/providers': api,
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/useProviders.js', import.meta.url),
      'utf8'
    ),
    { context }
  )
  await module.link((specifier) => {
    const namespace = mocks[specifier]
    assert.ok(namespace, specifier)
    return new SyntheticModule(
      Object.keys(namespace),
      function () {
        for (const [key, value] of Object.entries(namespace)) this.setExport(key, value)
      },
      { context }
    )
  })
  await module.evaluate()
  const state = module.namespace.useProviders()
  state.formRef.value = { validate: async () => true }
  state.accountFormRef.value = { validate: async () => true }
  return { state, saved, hooks, user }
}

for (const account of [false, true]) {
  test(`${account ? '账号' : '连接'}校验期间阻止重复提交和切换，校验失败可重试`, async () => {
    const { state, saved, hooks } = await harness()
    if (account) { state.select(connection('1')); state.startAccount() }
    else await state.start(connection('1'))
    let resolveValidation
    const formRef = account ? state.accountFormRef : state.formRef
    formRef.value = { validate: () => new Promise(resolve => { resolveValidation = resolve }) }
    const submit = account ? state.submitAccount : state.submit
    const first = submit()
    assert.equal(state.pending.value, true)
    assert.equal(hooks.leave(), false)
    await submit()
    state.close()
    await state.start(connection('2'))
    assert.equal(account ? state.accountOpen.value : state.open.value, true)
    assert.equal(state.editing.value?.id || state.selected.value.id, '1')
    resolveValidation(false)
    await first
    assert.equal(saved.length, 0)
    assert.equal(state.pending.value, false)
    formRef.value = { validate: async () => true }
    await submit()
    assert.equal(saved.length, 1)
    assert.equal(account ? saved[0][0].connectionId : saved[0][0], '1')
  })
  test(`${account ? '账号' : '连接'}校验后失去权限或卸载不发送写入`, async () => {
    for (const unmount of [false, true]) {
      const { state, saved, hooks, user } = await harness()
      if (account) { state.select(connection('1')); state.startAccount() }
      else await state.start(connection('1'))
      let resolveValidation
      const formRef = account ? state.accountFormRef : state.formRef
      formRef.value = { validate: () => new Promise(resolve => { resolveValidation = resolve }) }
      const pending = account ? state.submitAccount() : state.submit()
      if (unmount) hooks.unmount()
      else user.permissions = []
      resolveValidation(true)
      await pending
      assert.equal(saved.length, 0)
    }
  })
}

test('编辑使用最新并发版本和白名单配置，失败重试保留幂等键', async () => {
  const attempts = []
  const { state } = await harness({
    saveProviderConnection: async (...args) => {
      attempts.push(args)
      throw new Error('离线')
    },
  })
  await state.start(connection('1'))
  state.form.name = '新名称'
  await state.submit()
  await state.submit()
  assert.equal(attempts[0][0], '1')
  assert.equal(attempts[0][1].revision, '3')
  assert.equal(attempts[0][1].environment, undefined)
  assert.equal(attempts[0][1].config.bizId, 'op')
  assert.deepEqual([...attempts[0][1].config.allowedHosts], ['example.com'])
  assert.equal(attempts[0][2], attempts[1][2])
  state.form.name = '另一个名称'
  await state.submit()
  assert.notEqual(attempts[1][2], attempts[2][2])
  assert.equal(state.open.value, true)
  assert.equal(state.pending.value, false)
})

test('过期账号查询不会覆盖新选中的连接，提交使用当前连接身份', async () => {
  let oldResolve
  const { state, saved } = await harness({
    listProviderAccounts: ({ connectionId }) =>
      connectionId === '1'
        ? new Promise((resolve) => {
            oldResolve = resolve
          })
        : Promise.resolve({ rows: [{ id: 'new-account' }], total: 1 }),
  })
  state.select(connection('1'))
  state.select(connection('2'))
  await new Promise((resolve) => setImmediate(resolve))
  oldResolve({ rows: [{ id: 'old-account' }], total: 1 })
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.accounts.value[0].id, 'new-account')
  state.startAccount()
  Object.assign(state.accountForm, {
    accountCode: 'exact-account',
    region: 'eva',
    upstreamProject: 'exact-project',
  })
  state.select(connection('3'))
  await state.submitAccount()
  assert.equal(saved[0][0].connectionId, '2')
  assert.equal(saved[0][0].upstreamProject, 'exact-project')
})

test('关闭编辑再新建，不会被旧详情请求覆盖或留在加载状态', async () => {
  let resolveOld
  const { state } = await harness({
    getProviderConnection: () =>
      new Promise((resolve) => {
        resolveOld = resolve
      }),
  })
  const old = state.start(connection('1'))
  state.close()
  await state.start()
  resolveOld({ data: connection('1') })
  await old
  assert.equal(state.editing.value, null)
  assert.equal(state.form.name, '')
  assert.equal(state.preparing.value, false)
  assert.equal(state.open.value, true)
})
