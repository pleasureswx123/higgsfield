const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')
function setup(api = {}, grant = true) {
  const exports = {}, auth = vue.reactive({ token: 'a' })
  const roles = vue.ref([{ id: '2', name: '制作成员', canGrant: grant }])
  const code = ts.transpileModule(readFileSync('src/composables/useMemberManagement.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  runInNewContext(code, { exports, crypto: require('node:crypto'), require(id) {
    if (id === 'vue') return { ...vue, onBeforeUnmount() {} }
    if (id === '@/stores/auth') return { useAuthStore: () => auth }
    if (id === './useProjectWorkspace') return { useProjectMembers: () => ({ roles, ownershipRevision: vue.ref('7'), load: async () => {} }) }
    if (id === 'element-plus') return { ElMessage: { success() {}, error() {} }, ElMessageBox: { confirm: async () => {} } }
    return api
  } })
  const scope = vue.effectScope(), state = scope.run(() => exports.useMemberManagement('2'))
  state.formRef.value = { validate: async () => true }
  return { state, auth, close: () => scope.stop() }
}
test('修改查询账号后忽略旧候选响应', async () => {
  let resolve
  const c = setup({ findCandidate: () => new Promise(done => { resolve = done }) })
  c.state.account.value = 'first'
  const request = c.state.lookup()
  c.state.account.value = 'second'
  resolve({ data: { items: [{ userId: '1' }] } }); await request
  assert.equal(c.state.candidate.value, undefined)
  c.close()
})
test('添加失败重试保留幂等键并提交选定角色', async () => {
  const calls = []
  const c = setup({ addMember: async (...args) => { calls.push(args); if (calls.length === 1) throw Error('网络错误') } })
  c.state.candidate.value = { userId: '104', displayName: '制作成员甲' }
  c.state.roleId.value = '2'
  await c.state.add(); await c.state.add()
  assert.equal(calls.length, 2)
  assert.equal(calls[0][2], calls[1][2])
  assert.equal(calls[0][1].roleId, '2')
  assert.equal(calls[0][1].userId, '104')
  c.close()
})
test('无管理权限不提交角色变更，切换账号清除候选', async () => {
  let calls = 0
  const c = setup({ changeMember: async () => { calls++ } }, false)
  await c.state.modify({ userId: '104', roleId: '1', revision: '3' }, '2')
  assert.equal(calls, 0)
  c.state.candidate.value = { userId: '104' }; c.state.open.value = true
  c.auth.token = 'b'
  assert.equal(c.state.candidate.value, undefined)
  assert.equal(c.state.open.value, false)
  c.close()
})

test('Owner转让提交双版本且不能直接转让给Owner', async () => {
  const calls = []
  const c = setup({ transferOwnership: async (...args) => { calls.push(args) } })
  c.state.roles.value = [{ id: '1', code: 'owner', isCurrentRole: true, canGrant: false }, { id: '2', code: 'producer', canGrant: true }]
  await c.state.transfer({ userId: '1', roleId: '1', revision: '1', displayName: '所有者' })
  assert.equal(calls.length, 0)
  await c.state.transfer({ userId: '104', roleId: '2', revision: '3', displayName: '制作人' })
  assert.equal(calls.length, 1)
  assert.equal(calls[0][1].revision, '7')
  assert.equal(calls[0][1].targetRevision, '3')
  c.close()
})
