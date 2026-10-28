import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { ref, reactive, computed, watch, effectScope } from 'vue'
import { webcrypto } from 'node:crypto'
const tick = () => new Promise(done => setImmediate(done))
async function setup(api = {}, confirm = async () => {}) {
  const user = reactive({ token: 'one', permissions: ['member:manage'] }), hooks = {}, calls = []
  const context = createContext({ crypto: webcrypto })
  const mocks = {
    vue: { ref, reactive, computed, watch, onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    'element-plus': { ElMessageBox: { confirm } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/projects': {
      listStudioProjects: async () => ({ rows: [], total: 0 }),
      getProjectMembers: async () => ({ rows: [{ userId: '2' }], total: 1 }),
      getProjectRoles: async () => ({ data: { items: [{ id: '3', code: 'viewer', canGrant: true }] } }),
      findProjectCandidate: async () => ({ data: { items: [{ userId: '2' }] } }),
      addProjectMember: async (...args) => { calls.push(args) }, updateProjectMember: async (...args) => { calls.push(args) }, removeProjectMember: async (...args) => { calls.push(args) }, ...api,
    },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useProjectMembers.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () { for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value) }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useProjectMembers())
  state.selectProject({ id: '9', status: 'active' }); await tick()
  return { user, hooks, calls, state, close: () => { hooks.unmount(); scope.stop() } }
}
test('账号切换清空父级成员和弹窗，迟到列表不回填', async () => {
  let resolve
  const c = await setup({ getProjectMembers: () => new Promise(done => { resolve = done }) })
  c.state.form.account = '旧账号候选'; c.state.open.value = true
  c.user.token = 'two'
  assert.equal(c.state.selected.value, null); assert.equal(c.state.open.value, false)
  assert.equal(c.state.form.account, '')
  resolve({ rows: [{ userId: 'late' }], total: 100 }); await tick()
  assert.equal(c.state.members.value.length, 0); assert.equal(c.state.roles.value.length, 0); assert.equal(c.state.total.value, 0)
  c.close()
})
test('添加验证和修改确认等待期间撤权，不得发送成员写请求', async () => {
  let validate, confirm
  const c = await setup({}, () => new Promise(done => { confirm = done }))
  c.state.candidate.value = { userId: '2' }; c.state.form.roleId = '3'
  c.state.formRef.value = { validate: () => new Promise(done => { validate = done }) }
  const adding = c.state.add(); c.user.token = 'two'; validate(true); await adding
  assert.equal(c.calls.length, 0)
  c.state.selectProject({ id: '9', status: 'active' }); await tick()
  const modifying = c.state.modify({ userId: '2', roleId: '3' }, '4')
  c.user.permissions = []; confirm(); await modifying
  assert.equal(c.calls.length, 0); c.close()
})
test('旧保存响应不修改新账号视图，缓存恢复重新读取角色', async () => {
  let resolve
  const c = await setup({ addProjectMember: () => new Promise(done => { resolve = done }) })
  c.state.candidate.value = { userId: '2' }; c.state.form.roleId = '3'; c.state.formRef.value = { validate: async () => true }
  const pending = c.state.add(); await tick()
  assert.equal(c.hooks.leave(), false)
  c.user.token = 'two'; resolve(); await pending
  assert.equal(c.state.selected.value, null); assert.equal(c.state.members.value.length, 0)
  c.state.selectProject({ id: '9', status: 'active' }); await tick()
  c.hooks.deactivate(); assert.equal(c.state.canManage.value, false)
  c.hooks.activate(); await tick(); assert.equal(c.state.canManage.value, true)
  c.close()
})
