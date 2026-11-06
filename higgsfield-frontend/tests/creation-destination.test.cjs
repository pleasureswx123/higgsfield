const { test } = require('node:test')
const assert = require('node:assert/strict')
const vue = require('vue'), ts = require('typescript')
const { readFileSync } = require('node:fs'), { runInNewContext } = require('node:vm')
function setup(api = {}, allowed = true) {
  const exports = {}, auth = vue.reactive({ token: 'one' }), selected = vue.ref(null)
  const calls = [], hooks = {}
  runInNewContext(ts.transpileModule(readFileSync(require('node:path').join(__dirname, '../src/composables/useCreationDestination.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, Error, crypto: require('node:crypto').webcrypto,
    require(id) {
      if (id === 'vue') return { ...vue, onBeforeUnmount: fn => hooks.close = fn }
      if (id.includes('stores/auth')) return { useAuthStore: () => auth }
      if (id.includes('api/client')) return { ApiError: class extends Error {} }
      if (id.includes('api/folders')) return {
        listFolders: async () => api.list ? api.list() : ({ rows: [], total: 0, hasNext: false }),
        readFolder: async () => ({ data: { ancestors: [], folder: { name: '已选目录' } } }),
        createFolder: async (...args) => { calls.push(args); return api.create ? api.create(...args) : { data: { id: '8', name: args[1].name } } },
      }
      throw Error(id)
    },
  })
  return { state: exports.useCreationDestination('2', () => selected.value, () => allowed), auth, calls, selected, hooks }
}
test('空项目显示引导，选择已有目录后收起', async () => {
  const h = setup(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(h.state.emptyProject.value, true)
  assert.equal(h.state.generationBlock.value, '请先创建文件夹')
  h.selected.value = '9'; await vue.nextTick()
  assert.equal(h.state.emptyProject.value, false)
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(h.state.generationBlock.value, '')
})
test('无创建权限不发送写请求', async () => {
  const h = setup({}, false); await h.state.create('测试')
  assert.equal(h.calls.length, 0)
})
test('网络结果未知重试复用请求及幂等键，成功返回目录', async () => {
  let count = 0
  const h = setup({ create: async () => { if (!count++) throw Error('网络中断'); return { data: { id: '8' } } } })
  await h.state.create('第一幕')
  assert.equal(h.state.uncertain.value, true)
  const folder = await h.state.create('不应改变请求')
  assert.equal(folder.id, '8')
  assert.deepEqual(h.calls[0], h.calls[1])
  assert.equal(h.state.uncertain.value, false)
})
test('卸载后丢弃迟到的创建结果', async () => {
  let resolve
  const h = setup({ create: () => new Promise(r => resolve = r) })
  const pending = h.state.create('第一幕'); h.hooks.close(); resolve({ data: { id: '8' } })
  assert.equal(await pending, undefined)
})

test('目录检查期间和读取失败均阻止生成，有现有目录时解除限制', async () => {
  const failed = setup({ list: async () => { throw Error('网络中断') } })
  assert.equal(failed.state.generationBlock.value, '正在检查保存位置')
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(failed.state.generationBlock.value, '保存位置读取失败，请重新选择')
  const existing = setup({ list: async () => ({ rows: [{ id: '9' }], total: 1, hasNext: false }) })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(existing.state.generationBlock.value, '')
})
