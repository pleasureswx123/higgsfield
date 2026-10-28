import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { reactive, ref } from 'vue'
import { webcrypto } from 'node:crypto'

async function harness(change, permissions = ['*:*:*']) {
  const hooks = {},
    calls = []
  let refreshed = 0
  const context = createContext({ crypto: webcrypto, Error, window: { confirm: () => true } })
  const mocks = {
    vue: { reactive, ref, onMounted: () => {}, onDeactivated: () => {}, onBeforeUnmount: () => {} },
    'vue-router': {
      onBeforeRouteLeave: (fn) => {
        hooks.leave = fn
      },
    },
    '@/store/modules/user': { default: () => ({ permissions }) },
    '@/api/studio/credentials': {
      changeCredentialState: async (...args) => {
        calls.push(args)
        await change?.()
      },
    },
  }
  const module = new SourceTextModule(
    await readFile(
      new URL('../../src/composables/studio/useCredentialState.js', import.meta.url),
      'utf8'
    ),
    { context }
  )
  await module.link((specifier) => {
    const values = mocks[specifier]
    return new SyntheticModule(
      Object.keys(values),
      function () {
        for (const [key, value] of Object.entries(values)) this.setExport(key, value)
      },
      { context }
    )
  })
  await module.evaluate()
  const state = module.namespace.useCredentialState(async () => {
    refreshed++
  })
  state.formRef.value = { validate: async () => true }
  return { state, hooks, calls, refreshed: () => refreshed }
}
const row = { id: '8', revision: '3', state: 'active', versionNo: 2 }

test('失败重试保留幂等键，修改原因后重新分配，携带原始并发版本', async () => {
  const { state, calls } = await harness(() => {
    throw new Error('离线')
  })
  state.start(row, 'drain')
  row.revision = '4'
  state.form.reason = '  轮换密钥  '
  await state.submit()
  await state.submit()
  assert.equal(calls[0][2].revision, '3')
  assert.equal(calls[0][2].reason, '轮换密钥')
  assert.equal(calls[0][3], calls[1][3])
  state.form.reason = '维护'
  await state.submit()
  assert.notEqual(calls[1][3], calls[2][3])
  assert.equal(state.open.value, true)
})

test('异步校验期间阻止重复提交、关闭和离开，成功刷新列表', async () => {
  const { state, hooks, calls, refreshed } = await harness()
  let resolve
  state.formRef.value = {
    validate: () =>
      new Promise((done) => {
        resolve = done
      }),
  }
  state.start(row, 'revoke')
  state.form.reason = '泄露处理'
  const first = state.submit()
  await state.submit()
  state.close()
  assert.equal(state.open.value, true)
  assert.equal(hooks.leave(), false)
  resolve(true)
  await first
  assert.equal(calls.length, 1)
  assert.equal(refreshed(), 1)
  assert.equal(state.open.value, false)
})

test('权限与状态限制操作，表单失败不请求', async () => {
  const { state, calls } = await harness(undefined, ['credential:disable'])
  assert.equal(state.available(row, 'revoke'), false)
  assert.equal(state.available(row, 'disable'), false)
  assert.equal(state.available({ ...row, state: 'revoked' }, 'drain'), false)
  state.start(row, 'revoke')
  assert.equal(state.open.value, false)
  state.start(row, 'drain')
  state.formRef.value = {
    validate: async () => {
      throw new Error('必填')
    },
  }
  await state.submit()
  assert.equal(calls.length, 0)
  assert.equal(state.pending.value, false)
})
