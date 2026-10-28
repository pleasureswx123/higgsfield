import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { webcrypto } from 'node:crypto'
import { computed, reactive, ref, watch } from 'vue'
async function harness(create = async () => ({ data: { id: '99', accepted: true, state: 'pending' } })) {
 const calls = [], hooks = {}, user = reactive({ permissions: ['credential:test'] })
 const context = createContext({ crypto: webcrypto, Error, AbortController, window: { confirm: () => true, addEventListener() {}, removeEventListener() {} } })
 const mocks = {
  vue: { computed, reactive, ref, watch, onMounted() {}, onBeforeUnmount() {}, onDeactivated() {} },
  'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
  '@/store/modules/user': { default: () => user },
  '@/api/studio/credentials': {
   listCredentialTestModels: async () => ({ rows: [{ id: '2', name: '模型' }], total: 1 }),
   listTestCostCenters: async () => ({ rows: [{ id: '3', active: true }], total: 1 }),
   createCredentialTest: async (...args) => { calls.push(args); return create(...args) },
  },
 }
 const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useCredentialTest.js', import.meta.url), 'utf8'), { context })
 await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () {
  for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
 }, { context }))
 await module.evaluate()
 const state = module.namespace.useCredentialTest()
 state.start({ id: '8', state: 'draft', versionNo: 1 })
 await Promise.all([state.load(state.models), state.load(state.centers)])
 state.formRef.value = { validate: async () => true }
 Object.assign(state.form, { modelVersionId: '2', costCenterId: '3' })
 return { state, user, calls, hooks }
}

test('必须明确确认费用，受理后不能再次提交', async () => {
 const { state, calls } = await harness()
 await state.submit()
 assert.equal(calls.length, 0)
 state.form.acknowledgePotentialCharge = true
 await state.submit()
 await state.submit()
 assert.equal(calls.length, 1)
 assert.equal(calls[0][0], '8')
 assert.equal(calls[0][1].acknowledgePotentialCharge, true)
 assert.equal(state.receipt.value.state, 'pending')
})
test('失败重试保留幂等键，撤权清理申请状态', async () => {
 const { state, user, calls } = await harness(async () => { throw new Error('离线') })
 state.form.acknowledgePotentialCharge = true
 await state.submit()
 await state.submit()
 assert.equal(calls[0][2], calls[1][2])
 user.permissions = []
 assert.equal(state.open.value, false)
 assert.equal(state.models.rows.length, 0)
 await state.submit()
 assert.equal(calls.length, 2)
})
test('异步校验期间禁止重复申请和离开', async () => {
 const { state, calls, hooks } = await harness()
 state.form.acknowledgePotentialCharge = true
 let resolve
 state.formRef.value = { validate: () => new Promise(done => { resolve = done }) }
 const first = state.submit()
 await state.submit()
 state.close()
 assert.equal(state.open.value, true)
 assert.equal(hooks.leave(), false)
 resolve(true)
 await first
 assert.equal(calls.length, 1)
})
