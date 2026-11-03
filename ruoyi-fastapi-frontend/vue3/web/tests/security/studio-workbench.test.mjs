import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch, effectScope } from 'vue'
import { studioNavigation, labelStudioRoutes, menuDestination } from '../../src/utils/studioNavigation.js'
import { workbenchEntries, workbenchNext, workbenchRole, authorizedPaths } from '../../src/utils/studioWorkbench.js'

test('综合管理员识别合并职责，用户和部门入口各自要求对应权限', () => {
  assert.equal(workbenchRole(['hf_platform_finance_admin']), 'combined')
  assert.equal(workbenchEntries.find(row => row.key === 'users').permission, 'system:user:list')
  assert.equal(workbenchEntries.find(row => row.key === 'departments').path, '/system/dept')
})

const menu = children => [{ path: '/studio', meta: { title: '制作平台' }, children: children.map(path => ({ path, name: path, meta: { title: path } })) }]
test('授权菜单只重排不增权，主流程和高级设置分组且原路由不改', () => {
  const source = menu(['prices', 'provider-credentials', 'models', 'routing', 'provider-connections', 'calls', 'incidents'])
  const before = structuredClone(source)
  const result = studioNavigation(source)[0]
  assert.deepEqual(source, before)
  assert.deepEqual(result.children.map(row => row.meta.title), ['供应商与模型', '运行记录'])
  assert.deepEqual(labelStudioRoutes(source)[0].children.map(row => row.path), source[0].children.map(row => row.path))
  assert.equal(result.children.some(row => row.path === 'billing-events'), false)
  assert.equal(result.children.at(-1).alwaysShow, true)
  const internal = labelStudioRoutes(source)[0].children.filter(row => ['prices', 'models', 'routing', 'provider-credentials'].includes(row.path))
  assert.ok(internal.every(row => row.hidden))
  assert.ok(internal.every(row => row.meta.activeMenu === '/studio/provider-connections'))
  assert.ok(!result.children.some(row => row.meta.title === '高级设置'))
  assert.deepEqual(studioNavigation(menu(['billing-events']))[0].children.map(row => row.meta.title), ['用量与费用'])
})
test('嵌套菜单访问原绝对地址，高级连接模式可刷新直达', () => {
  assert.equal(menuDestination('/studio/advanced-menu', '/studio/prices'), '/studio/prices')
  assert.equal(menuDestination('/studio/routing', ''), '/studio/routing')
  assert.deepEqual(menuDestination('/studio/advanced-menu', '/studio/provider-connections', '{"mode":"advanced"}'),
    { path: '/studio/provider-connections', query: { mode: 'advanced' } })
  assert.equal(menuDestination('/', '/index'), '/index')
})
test('新管理员、继续接入、项目开放和只读费用角色获得不同建议，未知不当成零', () => {
  assert.equal(workbenchNext({ connections: 0 }, workbenchEntries).action, '接入第一个模型')
  assert.equal(workbenchNext({ connections: 1, published: 0 }, workbenchEntries).action, '继续已有接入')
  assert.equal(workbenchNext({ connections: 1, published: 1, platformModels: 0 }, workbenchEntries).path, '/studio/provider-connections')
  assert.equal(workbenchNext({ connections: null, published: null, platformModels: null }, workbenchEntries).heading, '从这里开始管理')
  assert.equal(workbenchNext({}, [workbenchEntries.find(row => row.key === 'billing')]).path, '/studio/billing-events')
  assert.equal(workbenchNext({}, []).path, undefined)
  assert.deepEqual(authorizedPaths(menu(['routing'])), ['/studio', '/studio/routing'])
})

async function harness(permissions, responses) {
  const hooks = {}, calls = []
  const user = reactive({ token: 'session-a', permissions, name: '管理员' })
  const store = reactive({ routes: menu(['provider-connections', 'models', 'routing', 'billing-events', 'calls', 'incidents']) })
  const context = createContext({ Date })
  const api = Object.fromEntries(['listProviderConnections', 'listModels', 'listModelVersions', 'listGovernedProjects', 'getPlatformRouting', 'listIncidents']
    .map(name => [name, async (...args) => { calls.push(name); return await responses[name](...args) }]))
  const vue = { computed, reactive, ref, watch, onMounted: fn => { hooks.mount = fn }, onActivated: fn => { hooks.activate = fn },
    onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
  const modules = {}
  for (const name of ['studioWorkbench', 'modelSetup']) {
    const m = new SourceTextModule(await readFile(new URL(`../../src/utils/${name}.js`, import.meta.url), 'utf8'), { context })
    await m.link(() => {}); await m.evaluate(); modules['@/utils/' + name] = m
  }
  const mocks = { vue, '@/store/modules/user': { default: () => user }, '@/store/modules/permission': { default: () => store }, '@/api/studio/workbench': api }
  const m = new SourceTextModule(await readFile(new URL('../../src/composables/studio/useWorkbench.js', import.meta.url), 'utf8'), { context })
  await m.link(name => modules[name] || new SyntheticModule(Object.keys(mocks[name]), function () {
    for (const [key, value] of Object.entries(mocks[name])) this.setExport(key, value)
  }, { context })); await m.evaluate()
  const scope = effectScope(), state = scope.run(() => m.namespace.useWorkbench())
  return { state, user, calls, hooks, close() { hooks.unmount(); scope.stop() } }
}
test('费用角色仅显示费用入口，不请求无权限的供应商和项目数据', async () => {
  const h = await harness(['billing:read'], {})
  await h.state.load()
  assert.deepEqual([...h.state.entries.value].map(row => row.key), ['billing'])
  assert.deepEqual(h.calls, [])
  assert.equal(h.state.facts.connections, null)
  h.close()
})
test('读取失败保持未知，其他成功指标仍可显示，不执行任何写入', async () => {
  const h = await harness(['provider:read', 'operations:read'], {
    listProviderConnections: async () => { throw new Error('连接中断') },
    listIncidents: async () => ({ total: 2, rows: [] }),
  })
  await h.state.load()
  assert.equal(h.state.facts.connections, null)
  assert.equal(h.state.facts.incidents, 2)
  assert.equal(h.state.issues.value.length, 1)
  assert.notEqual(h.state.next.value.action, '接入第一个模型')
  h.close()
})
test('切换账号时清空状态，迟到响应不能写回旧账号数据', async () => {
  let finish
  const h = await harness(['provider:read'], { listProviderConnections: () => new Promise(resolve => { finish = resolve }) })
  const pending = h.state.load()
  h.user.permissions = []
  finish({ total: 99, rows: [] }); await pending
  assert.equal(h.state.facts.connections, null)
  assert.equal(h.state.entries.value.length, 0)
  h.close()
})

test('费用角色即使有额外读取权限也不加载平台配置，平台角色不混入费用入口', async () => {
 const h = await harness(['provider:read', 'model:read', 'billing:read'], {})
 h.user.roles = ['hf_finance_admin']
 await h.state.load()
 assert.deepEqual(Array.from(h.state.entries.value, row => row.key), ['billing'])
 assert.equal(h.calls.length, 0)
 h.user.token = ''
 h.user.roles = ['hf_platform_admin']
 assert.deepEqual(Array.from(h.state.entries.value, row => row.key), ['setup'])
 h.close()
})
