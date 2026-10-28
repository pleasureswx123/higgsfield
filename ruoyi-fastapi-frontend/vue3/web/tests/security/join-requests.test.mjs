import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { webcrypto } from 'node:crypto'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

async function setup(api = {}) {
  const user = reactive({ token: 'one', permissions: ['member:manage'] }), hooks = {}, project = ref('9'), calls = []
  const context = createContext({ crypto: webcrypto, AbortController })
  const mocks = {
    vue: { computed, reactive, ref, watch, onBeforeUnmount: fn => { hooks.unmount = fn }, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn } },
    'vue-router': { onBeforeRouteLeave: fn => { hooks.leave = fn } },
    '@/store/modules/user': { default: () => user },
    '@/api/studio/joinRequests': { listJoinRequests: async () => ({ rows: [], total: 0 }), reviewJoinRequest: async (...args) => { calls.push(args); throw new Error('断网') }, ...api },
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useJoinRequests.js', import.meta.url), 'utf8'), { context })
  await module.link(name => new SyntheticModule(Object.keys(mocks[name]), function () { for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value) }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useJoinRequests(() => project.value, () => [{ id: '3', canGrant: true }], () => true, () => {}))
  state.formRef.value = { validate: async () => true }
  return { state, user, project, hooks, calls, close: () => { hooks.unmount(); scope.stop() } }
}

test('审批结果不明锁定原意图和键，明确业务拒绝可修正', async () => {
  const calls = []
  const c = await setup({ reviewJoinRequest: async (...args) => { calls.push(args); if (calls.length < 3) throw new Error('断网') } })
  c.state.start({ id: '9007199254740993', revision: '2', status: 'pending' }); c.state.form.roleId = '3'
  await c.state.submit(); assert.equal(c.state.locked.value, true); assert.equal(c.hooks.leave(), false)
  c.state.form.decision = 'rejected'; await c.state.submit()
  assert.equal(calls[0][2], calls[1][2]); assert.equal(calls[1][1].decision, 'approved')
  await c.state.submit(); assert.equal(c.state.target.value, undefined); assert.equal(c.state.locked.value, false)
  c.close()
  const d = await setup({ reviewJoinRequest: async () => { throw Object.assign(new Error('修订冲突'), { code: 601 }) } })
  d.state.start({ id: '1', revision: '1', status: 'pending' }); d.state.form.decision = 'rejected'
  await d.state.submit(); assert.equal(d.state.locked.value, false); assert.ok(d.state.actionError.value); d.close()
})

test('账号退出中断审批并丢弃迟到响应，权限撤回不重新读取', async () => {
  let resolve, signal, reads = 0
  const c = await setup({ listJoinRequests: async () => { reads++; return { rows: [], total: 0 } }, reviewJoinRequest: (id, data, key, current) => { signal = current; return new Promise(done => { resolve = done }) } })
  c.state.start({ id: '1', revision: '1', status: 'pending' }); c.state.form.decision = 'rejected'
  const pending = c.state.submit(); await new Promise(done => setImmediate(done))
  c.user.token = ''; c.user.permissions = []
  assert.equal(signal.aborted, true); assert.equal(c.state.target.value, undefined)
  const count = reads; resolve({}); await pending
  assert.equal(reads, count); assert.equal(c.state.rows.value.length, 0); c.close()
})

test('申请面板和成员页面通过Vue单文件组件编译', async () => {
  for (const file of ['JoinRequests.vue', 'index.vue']) {
    const filename = new URL(`../../src/views/studio/projectMembers/${file}`, import.meta.url)
    const { descriptor, errors } = parse(await readFile(filename, 'utf8'))
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: file })
    const template = compileTemplate({ id: file, source: descriptor.template.content, filename: file, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [])
  }
})

test('缓存停用取消请求，恢复后原键确认审批且不重复首次读取', async () => {
  let reads = 0
  const calls = []
  const c = await setup({ listJoinRequests: async () => { reads++; return { rows: [], total: 0 } }, reviewJoinRequest: (...args) => new Promise(resolve => calls.push({ args, resolve })) })
  c.hooks.activate(); assert.equal(reads, 1)
  c.state.start({ id: '1', revision: '1', status: 'pending' }); c.state.form.decision = 'rejected'
  const first = c.state.submit(); await new Promise(done => setImmediate(done))
  c.hooks.deactivate()
  assert.equal(calls[0].args[3].aborted, true)
  assert.equal(c.state.uncertain.value, true)
  await c.state.load(); assert.equal(reads, 1)
  calls[0].resolve({}); await first
  assert.equal(c.state.target.value.id, '1')
  c.hooks.activate(); assert.equal(reads, 2)
  const second = c.state.submit(); await new Promise(done => setImmediate(done))
  assert.equal(calls[0].args[2], calls[1].args[2])
  calls[1].resolve({}); await second
  assert.equal(c.state.locked.value, false); assert.equal(c.state.target.value, undefined)
  c.close()
})
