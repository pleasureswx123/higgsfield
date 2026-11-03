import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, ref, reactive, watch, effectScope } from 'vue'
import { modelHubState, toggleModelRoutes } from '../../src/utils/modelHub.js'
import { videoModels } from '../../src/utils/videoModels.js'

test('停用和重新启用保留供应商凭据及其他模型配置', () => {
  const config = { revision: '7', routes: [
    { modelId: '1', enabled: true, credentials: [{ credentialId: '9' }] },
    { modelId: '2', enabled: true, credentials: [{ credentialId: '9' }] },
  ] }
  const stopped = toggleModelRoutes(config, '1', false)
  assert.equal(config.routes[0].enabled, true)
  assert.equal(stopped.routes[0].enabled, false)
  assert.deepEqual(stopped.routes[1], config.routes[1])
  assert.equal(modelHubState({ id: '1', code: 'mm-imagen2', kind: 'image' }, [{ status: 'published' }], stopped.routes).label, '已停用')
  assert.deepEqual(toggleModelRoutes(stopped, '1', true), config)
  assert.throws(() => toggleModelRoutes(config, '3', true), /完成模型配置/)
})

test('视频目录覆盖九个供应商别名，稳定码符合平台规则且不误标启用', () => {
  assert.equal(videoModels.length, 9)
  assert.equal(new Set(videoModels.map(row => row.code)).size, 9)
  for (const model of videoModels) {
    assert.match(model.code, /^[a-z][a-z0-9_-]{0,99}$/)
    assert.equal(modelHubState(model, [], []).supported, true)
    assert.notEqual(modelHubState(model, [], []).tone, 'success')
  }
})

test('按模型分别显示开放、停用和待适配，未知状态不伪装成功', () => {
  const image = { id: '1', code: 'mm-imagen2', kind: 'image' }
  assert.equal(modelHubState(image, [{ status: 'published' }], null).label, '开放状态未读取')
  assert.equal(modelHubState(image, [{ status: 'published' }], []).label, '待全平台启用')
  assert.equal(modelHubState(image, [{ status: 'published' }], [{ modelId: '1', enabled: true, credentials: [{}] }]).tone, 'success')
  assert.equal(modelHubState(image, [{ status: 'disabled' }], []).label, '已停用')
  assert.equal(modelHubState({ id: '2', kind: 'video', code: 'new-video' }, [], []).label, '待适配')
})

test('同一供应商完整加载多个模型，刷新只读，权限失效清空列表', async () => {
  const hooks = {}, calls = [], user = reactive({ token: 'one', permissions: ['*:*:*'] })
  const page = rows => ({ rows, total: rows.length, hasNext: false })
  let failWrite = true
  const writes = []
  const api = {
    listProviderConnections: async () => page([{ id: '1', name: '共享供应商' }]),
    getPlatformRouting: async () => ({ data: { revision: '1', routes: [{ modelId: '10', enabled: true, credentials: [{}] }] } }),
    savePlatformRouting: async (payload, key) => { writes.push({ payload, key }); if (failWrite) throw new Error('网络中断') },
    listModels: async query => { assert.equal(query.connectionId, '1'); return page([
      { id: '10', displayName: '图片', code: 'mm-imagen2', kind: 'image' },
      { id: '11', displayName: '视频', code: 'new-video', kind: 'video' },
    ]) },
    listModelVersions: async id => { calls.push(id); return page([]) },
  }
  const context = createContext({ crypto: { randomUUID: () => 'fixed-key' } })
  const vue = { ref, computed, watch, onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn },
    onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
  const mocks = { vue, '@/store/modules/user': { default: () => user }, '@/api/studio/modelSetup': api }
  const modules = {}
  for (const name of ['videoModels', 'modelSetup', 'modelHub']) {
    const m = new SourceTextModule(await readFile(new URL(`../../src/utils/${name}.js`, import.meta.url), 'utf8'), { context })
    await m.link(path => modules[path]); await m.evaluate(); modules[`@/utils/${name}`] = m; modules[`./${name}.js`] = m
  }
  const module = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useModelHub.js', import.meta.url), 'utf8'), { context })
  await module.link(name => modules[name] || new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const scope = effectScope(), state = scope.run(() => module.namespace.useModelHub())
  await hooks.mount()
  assert.equal(state.models.value.length, 2)
  assert.deepEqual(calls, ['10', '11'])
  state.kind.value = 'video'; assert.equal(state.visible.value.length, 1)
  await state.load(); assert.equal(state.models.value.length, 2)
  const row = { id: '10', enabled: true }
  await state.toggle(row)
  assert.match(state.changeError.value, /网络中断/)
  failWrite = false
  await state.toggle(row)
  assert.equal(writes.length, 2)
  assert.equal(writes[0].key, writes[1].key)
  assert.deepEqual(writes[0].payload, writes[1].payload)
  assert.equal(writes[1].payload.routes[0].enabled, false)
  user.permissions = []
  assert.equal(state.models.value.length, 0)
  hooks.unmount(); scope.stop()
})
