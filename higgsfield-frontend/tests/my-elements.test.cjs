const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'),
  vue = require('vue')
const tick = async () => {
  await vue.nextTick()
  await new Promise((resolve) => setImmediate(resolve))
}
function harness() {
  const exports = {},
    calls = [],
    hooks = {},
    auth = vue.reactive({ token: 'one', user: { permissions: ['element:read'] } })
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/useMyElements.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
    ).outputText,
    {
      exports,
      AbortController,
      require(name) {
        if (name === 'vue')
          return {
            ...vue,
            onMounted: (fn) => {
              hooks.mount = fn
            },
            onActivated: (fn) => {
              hooks.activate = fn
            },
            onDeactivated: (fn) => {
              hooks.deactivate = fn
            },
            onBeforeUnmount: (fn) => {
              hooks.unmount = fn
            },
          }
        if (name.includes('stores/auth')) return { useAuthStore: () => auth }
        return {
          listElements: (...args) => new Promise((resolve) => calls.push({ args, resolve })),
        }
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() => exports.useMyElements())
  hooks.mount()
  hooks.activate()
  return {
    state,
    calls,
    hooks,
    auth,
    close() {
      hooks.unmount()
      scope.stop()
    },
  }
}
test('我的元素传递状态交集并保持mine范围，筛选回第一页只请求一次', async () => {
  const h = harness()
  assert.equal(h.calls.length, 1)
  h.calls[0].resolve({ rows: [], total: 50 })
  await tick()
  h.state.page.value = 2
  await tick()
  h.state.category.value = 'character'
  h.state.workStatus.value = 'approved'
  h.state.statusGroup.value = 'active'
  h.state.filter()
  await tick()
  assert.equal(h.calls.length, 3)
  const params = h.calls[2].args[1]
  assert.equal(params.scope, 'mine')
  assert.equal(params.pageNum, 1)
  assert.equal(params.workStatus, 'approved')
  assert.equal(params.statusGroup, 'active')
  assert.equal(params.category, 'character')
  assert.equal(h.calls[1].args[2].aborted, true)
  h.close()
})
test('缓存停用和账号切换清空正文并阻断迟到响应，激活只重新读取一次', async () => {
  const h = harness()
  h.hooks.deactivate()
  assert.equal(h.calls[0].args[2].aborted, true)
  h.calls[0].resolve({ rows: [{ id: 'old' }], total: 1 })
  await tick()
  assert.equal(h.state.rows.value.length, 0)
  h.hooks.activate()
  assert.equal(h.calls.length, 2)
  h.calls[1].resolve({ rows: [{ id: 'one' }], total: 1 })
  await tick()
  h.auth.token = 'two'
  assert.equal(h.state.rows.value.length, 0)
  assert.equal(h.state.total.value, 0)
  assert.equal(h.calls.length, 3)
  h.auth.token = ''
  assert.equal(h.calls[2].args[2].aborted, true)
  h.calls[2].resolve({ rows: [{ id: 'late' }], total: 1 })
  await tick()
  assert.equal(h.state.rows.value.length, 0)
  assert.equal(h.calls.length, 3)
  h.close()
})

test('来源范围切换回第一页并取消旧请求，晚到响应不能覆盖收藏筛选', async () => {
  const h = harness()
  h.calls[0].resolve({ rows: [], total: 60 })
  await tick()
  h.state.page.value = 2
  await tick()
  h.state.mineFilter.value = 'favorites'
  h.state.filter()
  await tick()
  assert.equal(h.calls.length, 3)
  assert.equal(h.calls[2].args[1].mineFilter, 'favorites')
  assert.equal(h.calls[2].args[1].pageNum, 1)
  assert.equal(h.calls[1].args[2].aborted, true)
  h.calls[1].resolve({ rows: [{ id: 'old' }], total: 60 })
  await tick()
  assert.equal(h.state.rows.value.length, 0)
  h.calls[2].resolve({ rows: [{ id: 'favorite' }], total: 1 })
  await tick()
  assert.equal(h.state.rows.value[0].id, 'favorite')
  h.state.mineFilter.value = 'created'
  h.state.filter()
  await tick()
  assert.equal(h.calls[3].args[1].mineFilter, 'created')
  h.close()
})

test('收藏减少导致末页越界时保留筛选并等待有效页，空集合不重复请求', async () => {
  const h = harness()
  h.calls[0].resolve({ rows: [], total: 61 })
  await tick()
  h.state.mineFilter.value = 'favorites'
  h.state.search.value = '角色'
  h.state.page.value = 3
  await tick()
  const refreshing = h.state.refresh()
  h.calls[2].resolve({ rows: [], total: 31 })
  await tick()
  assert.equal(h.state.page.value, 2)
  assert.equal(h.calls.length, 4)
  assert.equal(h.calls[3].args[1].pageNum, 2)
  assert.equal(h.calls[3].args[1].pageSize, 30)
  assert.equal(h.calls[3].args[1].mineFilter, 'favorites')
  assert.equal(h.calls[3].args[1].q, '角色')
  assert.equal(h.state.loading.value, true)
  h.calls[3].resolve({ rows: [{ id: 'remaining' }], total: 31 })
  await refreshing
  assert.equal(h.state.rows.value[0].id, 'remaining')
  assert.equal(h.state.loading.value, false)
  const empty = h.state.refresh()
  h.calls[4].resolve({ rows: [], total: 0 })
  await empty
  await tick()
  assert.equal(h.state.page.value, 1)
  assert.equal(h.calls.length, 5)
  assert.equal(h.state.total.value, 0)
  h.close()
})

test('回退页请求期间退出会取消读取，迟到结果不能回填', async () => {
  const h = harness()
  h.calls[0].resolve({ rows: [], total: 61 })
  await tick()
  h.state.page.value = 3
  await tick()
  h.calls[1].resolve({ rows: [], total: 1 })
  await tick()
  assert.equal(h.calls.length, 3)
  h.auth.token = ''
  assert.equal(h.calls[2].args[2].aborted, true)
  h.calls[2].resolve({ rows: [{ id: 'late' }], total: 1 })
  await tick()
  assert.equal(h.state.rows.value.length, 0)
  assert.equal(h.state.total.value, 0)
  assert.equal(h.state.loading.value, false)
  h.close()
})

test('清除全部筛选只请求一次并恢复默认来源，空态依据已执行查询', async () => {
  const h = harness()
  h.calls[0].resolve({ rows: [], total: 0 })
  await tick()
  h.state.search.value = '未提交的输入'
  assert.equal(h.state.hasFilters.value, true)
  assert.equal(h.state.filteredResult.value, false)
  h.state.mineFilter.value = 'favorites'
  h.state.category.value = 'character'
  h.state.workStatus.value = 'approved'
  h.state.statusGroup.value = 'active'
  h.state.page.value = 2
  await tick()
  h.calls[1].resolve({ rows: [], total: 31 })
  await tick()
  assert.equal(h.state.filteredResult.value, true)
  h.state.clearFilters()
  await tick()
  assert.equal(h.calls.length, 3)
  const query = h.calls[2].args[1]
  assert.equal(query.pageNum, 1)
  assert.equal(query.mineFilter, 'all')
  assert.equal(query.q, '')
  assert.equal(query.category, undefined)
  assert.equal(query.workStatus, undefined)
  assert.equal(query.statusGroup, undefined)
  assert.equal(h.state.hasFilters.value, false)
  h.calls[2].resolve({ rows: [], total: 0 })
  await tick()
  assert.equal(h.state.filteredResult.value, false)
  h.close()
})
