const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
class ApiError extends Error { constructor(message, code, errorCode) { super(message); this.code = code; this.errorCode = errorCode } }
const data = (id = '1') => ({ targetId: id, versionId: 'v1', revision: '1', workStatus: 'review', performerId: null, performerName: null, canAssign: true, reviewVerified: false, allowedActions: ['request_changes', 'approve'], history: [] })
function setup(api = {}) {
  const exports = {}, hooks = {}, calls = [], changes = [], target = vue.reactive({ kind: 'asset', id: '1', projectId: 'p', versionId: 'v1' }), dirty = vue.ref(false)
  const auth = vue.reactive({ token: 'a', user: { user: { userId: 'u' }, permissions: ['asset:edit'] } })
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/useProduction.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, Error, AbortController, window: { addEventListener() {}, removeEventListener() {} }, crypto: { randomUUID }, require(id) {
      if (id === 'vue-router') return { onBeforeRouteLeave: fn => hooks.leave = fn, onBeforeRouteUpdate: fn => hooks.update = fn }
      if (id === 'vue') return { ...vue, onBeforeUnmount: fn => hooks.unmount = fn }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === '@/api/client') return { ApiError }
      return {
        readProduction: async (kind, id) => ({ data: data(id) }),
        executeProduction: async (...args) => { calls.push(args); return { data: { ...data(), revision: '2' } } },
        assignProduction: async (...args) => { calls.push(args); return { data: data() } },
        readRoles: async () => ({ data: { items: [{ id: 'maker', code: 'producer', productionKinds: ['asset', 'element'] }, { id: 'reader', code: 'viewer', productionKinds: [] }] } }),
        readMembers: async () => ({ rows: [{ userId: 'u1', roleId: 'maker' }, { userId: 'u2', roleId: 'reader' }], total: 2 }),
        ...api,
      }
    },
  })
  let scope = vue.effectScope()
  const create = () => scope.run(() => exports.useProduction(() => target, () => dirty.value, value => changes.push(value)))
  const state = create()
  return { state, target, dirty, calls, changes, hooks, auth,
    remount: () => { hooks.unmount(); scope.stop(); scope = vue.effectScope(); return create() },
    close: () => { hooks.unmount(); scope.stop() },
  }
}
const flush = () => new Promise(resolve => setImmediate(resolve))
test('旧版本与未保存输入不能提交，退回必须有意见，分配排除查看者', async () => {
  const c = setup(); await flush()
  assert.equal(c.state.members.value.length, 1)
  c.target.versionId = 'old'; await c.state.run('approve'); assert.equal(c.calls.length, 0)
  c.target.versionId = 'v1'; c.dirty.value = true; await c.state.run('approve'); assert.equal(c.calls.length, 0)
  c.dirty.value = false; await c.state.run('request_changes'); assert.match(c.state.error.value, /修改意见/)
  c.state.reason.value = '调整光线'; await c.state.run('request_changes')
  assert.equal(c.calls[0][2].versionId, 'v1'); assert.equal(c.calls[0][2].reason, '调整光线')
  assert.equal(c.changes.length, 1); c.close()
})

test('刷新读取失败清除旧操作授权，重试成功前不能提交', async () => {
  let denied = false
  const c = setup({ readProduction: async () => { if (denied) throw new ApiError('权限已变化', 403); return { data: data() } } })
  await flush(); denied = true; await c.state.load()
  assert.equal(c.state.state.value, undefined)
  await c.state.run('approve'); assert.equal(c.calls.length, 0)
  denied = false; await c.state.load(); assert.equal(c.state.blocked.value, false); c.close()
})

test('成员读取失败不阻塞审核，分配独立提示且不使用旧候选', async () => {
  const c = setup({ readMembers: async () => { throw new Error('成员加载失败') } })
  await flush()
  assert.equal(c.state.error.value, '')
  assert.match(c.state.assignmentError.value, /成员加载失败/)
  await c.state.run(undefined, true); assert.equal(c.calls.length, 0)
  await c.state.run('approve'); assert.equal(c.calls.length, 1); c.close()
})

test('系统权限变化重新读取动作，登出不继续读取制作内容', async () => {
  let reads = 0
  const c = setup({ readProduction: async () => { reads++; return { data: data() } } })
  await flush(); c.auth.user.permissions = []; await flush(); assert.equal(reads, 2)
  c.auth.token = ''; await flush(); assert.equal(reads, 2)
  assert.equal(c.state.state.value, undefined); assert.equal(c.hooks.leave(), true); c.close()
})
test('分配按实际制作权限而非角色名称筛选，自定义授权保持一致', async () => {
  const c = setup({ readRoles: async () => ({ data: { items: [
    { id: 'maker', code: 'producer', productionKinds: ['element'] },
    { id: 'reader', code: 'viewer', productionKinds: ['asset'] },
  ] } }) })
  await flush()
  assert.deepEqual(Array.from(c.state.members.value, member => member.userId), ['u2'])
  c.close()
})
test('网络未知结果保留意见和原幂等键，再次点击只重放原命令', async () => {
  const calls = []
  const c = setup({ executeProduction: async (...args) => { calls.push(args); if (calls.length === 1) throw new Error('网络中断'); return { data: data() } } })
  await flush(); c.state.reason.value = '修改构图'; await c.state.run('request_changes')
  assert.equal(c.state.reason.value, '修改构图')
  await c.state.run('approve')
  assert.equal(calls[0][3], calls[1][3]); assert.equal(calls[1][2].action, 'request_changes')
  assert.equal(c.state.intent.value, undefined); c.close()
})
test('切换对象后旧请求返回不能污染新对象或触发错误的刷新', async () => {
  let resolve
  const c = setup({ executeProduction: () => new Promise(done => resolve = done) })
  await flush(); const pending = c.state.run('approve'); c.target.id = '2'; await flush()
  resolve({ data: data('1') }); await pending
  assert.equal(c.state.state.value.targetId, '2'); assert.equal(c.changes.length, 0); c.close()
})
test('明确拒绝保留意见，允许刷新修订并重新提交', async () => {
  const c = setup({ executeProduction: async () => { throw new ApiError('版本冲突', 601, 'REVISION_CONFLICT') } })
  await flush(); c.state.reason.value = '补充细节'; await c.state.run('request_changes')
  assert.equal(c.state.intent.value, undefined); assert.equal(c.state.reason.value, '补充细节')
  await c.state.load(); assert.equal(c.state.reason.value, '补充细节'); c.close()
})

test('未提交意见按对象与版本隔离，关闭卸载后恢复，同版成功提交或明确清除才丢弃', async () => {
  const c = setup(); await flush()
  c.state.reason.value = '需要保留的意见'
  assert.equal(c.hooks.leave(), true)
  c.target.id = '2'; await flush()
  assert.equal(c.state.reason.value, '')
  c.state.reason.value = '第二个对象'
  c.target.id = '1'; await flush()
  assert.equal(c.state.reason.value, '需要保留的意见')
  c.target.versionId = 'v2'
  assert.equal(c.state.reason.value, '')
  c.target.versionId = 'v1'
  assert.equal(c.state.reason.value, '需要保留的意见')
  const reopened = c.remount(); await flush()
  assert.equal(reopened.reason.value, '需要保留的意见')
  reopened.clearDraft()
  assert.equal(c.remount().reason.value, '')
  const again = c.remount(); await flush()
  again.reason.value = '最终反馈'
  await again.run('request_changes')
  assert.equal(c.remount().reason.value, '')
  c.close()
})
