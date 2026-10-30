const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'),
  vue = require('vue')
class ApiError extends Error {
  constructor(message, code) {
    super(message)
    this.code = code
  }
}
const tick = () => new Promise((done) => setImmediate(done))
const timeUtils = {}
runInNewContext(
  ts.transpileModule(readFileSync(join(__dirname, '../src/utils/commentVideoTime.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
  { exports: timeUtils },
)
const recovery = {}
runInNewContext(
  ts.transpileModule(readFileSync(join(__dirname, '../src/utils/commentRecovery.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
  { exports: recovery, structuredClone },
)
test.beforeEach(() => recovery.clearCommentRecovery())

test('异步表单校验只提交已校验的主题和编辑内容', async () => {
  for (const change of [c => { c.state.threadId.value = 'other' }, c => { c.state.body.value = '新正文' },
    c => { c.state.videoTime.value = '2' }, c => { c.state.updateAnnotations([{ shape: 'point', geometry: { x: 0.5, y: 0.5 } }]) }]) {
    const c = await setup(); let validate
    c.state.body.value = '待校验正文'
    c.state.form.value = { validate: () => new Promise(resolve => { validate = resolve }) }
    const operation = c.state.mutate('save'); change(c); validate(true); await operation
    assert.equal(c.calls.length, 0); assert.equal(c.state.saving.value, false); c.close()
  }
})

test('丢弃确认期间的新编辑和主题变化不会触发原界面动作', async () => {
  for (const change of [c => { c.state.body.value = '继续编辑' }, c => { c.state.threadId.value = 'other' },
    c => { c.target.value = { outputId: 'other' } }, c => { c.auth.token = 'two' }]) {
    let confirm, applied = 0
    const c = await setup({ confirm: () => new Promise(resolve => { confirm = resolve }) })
    c.state.body.value = '未保存'
    const operation = c.state.runConfirmed(() => { applied++ }); change(c); confirm(); await operation
    assert.equal(applied, 0); c.close()
  }
})

test('无需弹窗的异步间隙也隔离媒体切换，稳定上下文允许动作', async () => {
  const c = await setup(); let applied = 0
  const operation = c.state.runConfirmed(() => { applied++ })
  c.target.value = { outputId: 'other' }; await operation; assert.equal(applied, 0)
  await c.state.runConfirmed(() => { applied++ }); assert.equal(applied, 1); c.close()
})
async function setup(overrides = {}) {
  const visible = vue.ref(true)
  const exports = {},
    hooks = {},
    calls = [],
    auth = vue.reactive({ token: 'one', user: { permissions: ['*:*:*'] } }),
    target = vue.ref({ outputId: '9007199254740993' })
  const api = {
    ApiError,
    listCommentThreads: async () => ({ rows: [], total: 0 }),
    listComments: async () => ({ rows: [], total: 0 }),
    createCommentThread: async () => ({ data: { id: '12' } }),
    postComment: async (...args) => {
      calls.push(args)
      return { data: { id: '13' } }
    },
    changeComment: async (...args) => {
      calls.push(args)
      return { data: { id: '13' } }
    },
    ...overrides,
  }
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/useMediaComments.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS } },
    ).outputText,
    {
      exports,
      AbortController,
      window: {
        addEventListener: (name, fn) => { hooks[name] = fn },
        removeEventListener: (name, fn) => { if (hooks[name] === fn) delete hooks[name] },
      },
      crypto: { randomUUID },
      require(id) {
        if (id === 'vue')
          return {
            ...vue,
            onActivated: (fn) => {
              hooks.activate = fn
            },
            onBeforeUnmount: (fn) => {
              hooks.unmount = fn
            },
            onDeactivated: (fn) => {
              hooks.deactivate = fn
            },
          }
        if (id === 'vue-router')
          return {
            onBeforeRouteLeave: (fn) => {
              hooks.leave = fn
            },
            onBeforeRouteUpdate: (fn) => {
              hooks.update = fn
            },
          }
        if (id === 'element-plus')
          return {
            ElMessageBox: {
              confirm:
                overrides.confirm ||
                (async () => {
                  throw new Error('取消')
                }),
            },
          }
        if (id === '@/utils/commentRecovery') return recovery
        if (id === '@/utils/commentVideoTime') return timeUtils
        if (id === '@/stores/auth') return { useAuthStore: () => auth }
        return api
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() =>
      exports.useMediaComments(
        () => target.value,
        () => 'video',
        () => visible.value,
      ),
    )
  state.form.value = { validate: async () => true }
  if (!state.uncertain.value) state.threadId.value = '12'
  await tick()
  return {
    visible,
    state,
    hooks,
    calls,
    target,
    auth,
    close: () => {
      hooks.unmount()
      scope.stop()
    },
  }
}
test('编辑保留既有标注，回复携带固定父评论ID', async () => {
  const c = await setup()
  c.state.edit({ id: '33', revision: '2', body: '旧正文', annotations: [{ shape: 'point' }] })
  c.state.body.value = '新正文'
  await c.state.mutate('save')
  assert.equal(c.calls[0][0], '33')
  assert.equal(c.calls[0][1].revision, '2')
  assert.equal('annotations' in c.calls[0][1], false)
  c.state.reply({ id: '44' })
  c.state.body.value = '回复'
  await c.state.mutate('save')
  assert.equal(c.calls[1][1].parentId, '44')
  c.close()
})
test('响应不明锁定编辑并复用原键重试，不重复创建', async () => {
  const calls = []
  const c = await setup({
    postComment: async (...args) => {
      calls.push(args)
      if (calls.length === 1) throw new ApiError('断网', 0)
      return { data: { id: '13' } }
    },
  })
  c.state.body.value = '同一评论'
  await c.state.mutate('save')
  assert.equal(c.state.locked.value, true)
  assert.equal(await c.hooks.leave(), false)
  c.state.edit({ id: '99', body: '不得切换' })
  assert.equal(c.state.editing.value, undefined)
  await c.state.retry()
  assert.equal(calls[0][2], calls[1][2])
  assert.equal(c.state.uncertain.value, false)
  c.close()
})

test('未发送正文或标注离开需确认，取消保留输入，未改动编辑无需提示', async () => {
  let prompts = 0,
    accept = false
  const c = await setup({
    confirm: async () => {
      prompts++
      if (!accept) throw new Error('取消')
    },
  })
  assert.equal(await c.state.confirmLeave(), true)
  c.state.edit({ id: '33', revision: '1', body: '原文', annotations: [] })
  assert.equal(await c.state.confirmLeave(), true)
  assert.equal(prompts, 0)
  c.state.body.value = '修改内容'
  assert.equal(await c.hooks.leave(), false)
  assert.equal(c.state.body.value, '修改内容')
  accept = true
  assert.equal(await c.state.confirmLeave(), true)
  c.state.resetEditor()
  c.state.updateAnnotations([{ shape: 'point', geometry: { x: 0.2, y: 0.3 } }])
  assert.equal(c.state.dirty.value, true)
  assert.equal(await c.state.confirmLeave(), true)
  assert.equal(prompts, 3)
  c.close()
})

test('离开确认等待期间账号改变或开始提交，迟到确认不能放行', async () => {
  let resolve
  const c = await setup({
    confirm: () =>
      new Promise((done) => {
        resolve = done
      }),
  })
  c.state.body.value = '旧账号内容'
  const pending = c.state.confirmLeave()
  c.auth.token = 'two'
  resolve()
  assert.equal(await pending, false)
  c.state.body.value = '新内容'
  const next = c.state.confirmLeave()
  c.state.saving.value = true
  resolve()
  assert.equal(await next, false)
  c.close()
})
test('切换目标后旧列表不回填，账号变化清除正文和结果', async () => {
  const resolvers = []
  const c = await setup({ listComments: () => new Promise((done) => resolvers.push(done)) })
  c.state.body.value = '私密正文'
  c.target.value = { assetVersionId: '55' }
  await tick()
  resolvers[0]({ rows: [{ id: 'old' }], total: 1 })
  await tick()
  assert.equal(c.state.rows.value.length, 0)
  assert.equal(c.state.body.value, '')
  c.state.body.value = '另一个输入'
  c.auth.token = 'two'
  assert.equal(c.state.body.value, '')
  assert.equal(c.state.threadId.value, '')
  c.close()
})

test('同值目标保留编辑内容，切换媒体从第一页读取主题', async () => {
  const pages = []
  const c = await setup({
    listCommentThreads: async (target, page) => {
      pages.push({ ...target, page })
      return { rows: [], total: 0 }
    },
  })
  c.state.threadPage.value = 4
  c.state.page.value = 3
  c.state.body.value = '未提交内容'
  await tick()
  c.target.value = { outputId: '9007199254740993' }
  await tick()
  assert.equal(c.state.body.value, '未提交内容')
  assert.equal(c.state.threadPage.value, 4)
  c.target.value = { assetVersionId: '55' }
  await tick()
  assert.equal(c.state.threadPage.value, 1)
  assert.equal(c.state.page.value, 1)
  assert.equal(c.state.body.value, '')
  assert.ok(pages.filter((row) => row.assetVersionId === '55').every((row) => row.page === 1))
  assert.ok(pages.some((row) => row.assetVersionId === '55'))
  c.close()
})

test('主题和评论读取失败独立展示，重试清理旧错误而不覆盖提交错误', async () => {
  let fail = true
  const c = await setup({
    listCommentThreads: async () => {
      if (fail) throw new Error('主题拒绝')
      return { rows: [{ id: '12' }], total: 1 }
    },
    listComments: async () => {
      if (fail) throw new Error('评论拒绝')
      return { rows: [], total: 0 }
    },
  })
  assert.ok(c.state.threadError.value)
  assert.ok(c.state.commentsError.value)
  assert.equal(c.state.threadLoading.value, false)
  assert.equal(c.state.loading.value, false)
  c.state.error.value = '提交结果仍需处理'
  c.state.body.value = '保留输入'
  fail = false
  await Promise.all([c.state.loadThreads(), c.state.refresh()])
  assert.equal(c.state.threadError.value, '')
  assert.equal(c.state.commentsError.value, '')
  assert.equal(c.state.threadTotal.value, 1)
  assert.equal(c.state.error.value, '提交结果仍需处理')
  assert.equal(c.state.body.value, '保留输入')
  c.close()
})

test('旧主题请求完成不能结束新请求的加载状态，离开清理加载标记', async () => {
  const pending = []
  const c = await setup({ listCommentThreads: () => new Promise((done) => pending.push(done)) })
  assert.equal(c.state.threadLoading.value, true)
  const latest = c.state.loadThreads()
  pending[0]({ rows: [{ id: 'old' }], total: 99 })
  await tick()
  assert.equal(c.state.threadLoading.value, true)
  assert.equal(c.state.threadTotal.value, 0)
  pending[1]({ rows: [{ id: 'new' }], total: 1 })
  await latest
  assert.equal(c.state.threadLoading.value, false)
  assert.equal(c.state.threads.value[0].id, 'new')
  const leaving = c.state.loadThreads()
  c.close()
  assert.equal(c.state.threadLoading.value, false)
  pending[2]({ rows: [{ id: 'late' }], total: 1 })
  await leaving
  assert.equal(c.state.threads.value.length, 0)
})
test('账号切换中断写请求，迟到成功不能填回提示', async () => {
  let resolve, signal
  const c = await setup({
    postComment: (...args) => {
      signal = args[3]
      return new Promise((done) => {
        resolve = done
      })
    },
  })
  c.state.body.value = '正文'
  const pending = c.state.mutate('save')
  await tick()
  c.auth.token = 'two'
  resolve({ data: { id: '13' } })
  await pending
  assert.equal(signal.aborted, true)
  assert.equal(c.state.notice.value, '')
  c.close()
})

test('关闭后重建面板恢复原正文、主题和幂等键，成功后清除恢复记录', async () => {
  const calls = []
  const first = await setup({
    postComment: async (...args) => {
      calls.push(args)
      throw new ApiError('断网', 0)
    },
  })
  first.state.body.value = '必须原样恢复'
  await first.state.mutate('save')
  first.close()
  const second = await setup({
    postComment: async (...args) => {
      calls.push(args)
      return { data: { id: '13' } }
    },
  })
  assert.equal(second.state.uncertain.value, true)
  assert.equal(second.state.body.value, '必须原样恢复')
  assert.equal(second.state.threadId.value, '12')
  await second.state.retry()
  assert.equal(calls[0][2], calls[1][2])
  assert.equal(JSON.stringify(calls[0][1]), JSON.stringify(calls[1][1]))
  second.close()
  const third = await setup()
  assert.equal(third.state.uncertain.value, false)
  third.close()
})
test('请求途中关闭，重开仍可确认；旧账号结果不能清除新账号记录', async () => {
  let resolve
  const first = await setup({
    postComment: () =>
      new Promise((done) => {
        resolve = done
      }),
  })
  first.state.body.value = '发送中'
  const pending = first.state.mutate('save')
  await tick()
  first.close()
  const second = await setup()
  assert.equal(second.state.uncertain.value, true)
  second.auth.token = 'two'
  second.close()
  recovery.readCommentRecovery('two', 'target')
  recovery.saveCommentRecovery('two', 'target', {
    key: 'new',
    signature: 'new',
    mode: 'save',
    threadId: '1',
    body: '新账号',
  })
  resolve({ data: { id: '13' } })
  await pending
  assert.equal(recovery.readCommentRecovery('two', 'target').key, 'new')
})
test('同目标另一个面板不能覆盖尚未确认的请求', async () => {
  const first = await setup(),
    second = await setup({
      postComment: async () => {
        throw new ApiError('断网', 0)
      },
    })
  second.state.body.value = '另一个面板正在处理'
  await second.state.mutate('save')
  first.state.body.value = '不得创建第二条'
  await first.state.mutate('save')
  assert.equal(first.calls.length, 0)
  assert.equal(first.state.body.value, '另一个面板正在处理')
  first.close()
  second.close()
})

test('视频时间精确字符串提交，编辑保留时间，失败重开恢复原时间', async () => {
  const calls = []
  const c = await setup({
    postComment: async (...args) => {
      calls.push(args)
      throw new ApiError('断网', 0)
    },
  })
  c.state.body.value = '定位'
  c.state.videoTime.value = '12.000001'
  await c.state.mutate('save')
  c.close()
  const next = await setup({
    postComment: async (...args) => {
      calls.push(args)
      return { data: { id: '13' } }
    },
  })
  assert.equal(next.state.videoTime.value, '12.000001')
  await next.state.retry()
  assert.equal(calls[1][1].videoTime, '12.000001')
  assert.equal(calls[0][2], calls[1][2])
  next.state.edit({ id: '13', revision: '1', body: '定位', videoTime: '12.000001' })
  next.state.body.value = '只改正文'
  await next.state.mutate('save')
  assert.equal('videoTime' in next.calls[0][1], false)
  next.close()
})
test('时间输入不接受科学计数法、负数或超精度，播放器取点到六位', () => {
  for (const value of ['-1', 'NaN', '1e2', '.5', '1.0000001', '1000000000000', ' 1', '01'])
    assert.equal(timeUtils.validCommentVideoTime(value), false, value)
  for (const value of ['0', '0.000001', '999999999999.999999'])
    assert.equal(timeUtils.validCommentVideoTime(value), true)
  assert.equal(timeUtils.playerTimeToComment(12.1234567), '12.123457')
  assert.equal(timeUtils.playerTimeToComment(0), '0')
  assert.equal(timeUtils.playerTimeToComment(Infinity), '')
})

test('显式清空标注才提交空数组，编辑副本不能修改原评论', async () => {
  const annotation = {
    shape: 'point',
    geometry: { x: 0.5, y: 0.5 },
    color: '#ff0000',
    sourceWidth: 100,
    sourceHeight: 80,
  }
  const original = { id: '33', revision: '2', body: '带标注', annotations: [annotation] }
  const c = await setup()
  c.state.edit(original)
  c.state.updateAnnotations([])
  c.state.body.value = '已清空'
  await c.state.mutate('save')
  assert.equal(c.calls[0][1].annotations.length, 0)
  assert.equal(original.annotations.length, 1)
  c.close()
})
test('图片标注随未确认请求重开恢复，重试保持原坐标及幂等键', async () => {
  const calls = []
  const annotation = {
    shape: 'rect',
    geometry: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
    color: '#ff0000',
    sourceWidth: 100,
    sourceHeight: 80,
  }
  const c = await setup({
    postComment: async (...args) => {
      calls.push(args)
      throw new ApiError('断网', 0)
    },
  })
  c.state.body.value = '框选区域'
  c.state.updateAnnotations([annotation])
  await c.state.mutate('save')
  c.close()
  const next = await setup({
    postComment: async (...args) => {
      calls.push(args)
      return { data: { id: '13' } }
    },
  })
  assert.equal(next.state.annotations.value[0].geometry.width, 0.3)
  await next.state.retry()
  assert.equal(calls[0][2], calls[1][2])
  assert.equal(JSON.stringify(calls[0][1]), JSON.stringify(calls[1][1]))
  next.close()
})

test('评论408和幂等处理中保留原请求，缓存恢复后使用相同正文与键', async () => {
  for (const failure of [
    new ApiError('超时', 408),
    Object.assign(new ApiError('处理中', 601), { errorCode: 'IDEMPOTENCY_IN_PROGRESS' }),
  ]) {
    const calls = []
    const c = await setup({
      postComment: async (...args) => {
        calls.push(args)
        if (calls.length === 1) throw failure
        return { data: { id: '13' } }
      },
    })
    c.state.body.value = '原评论'
    await c.state.mutate('save')
    assert.equal(c.state.uncertain.value, true)
    assert.equal(await c.hooks.update({ fullPath: '/new' }, { fullPath: '/old' }), false)
    c.hooks.deactivate()
    await c.state.retry()
    assert.equal(calls.length, 1)
    c.hooks.activate()
    await tick()
    await c.state.retry()
    assert.equal(calls.length, 2)
    assert.equal(calls[0][2], calls[1][2])
    assert.equal(calls[1][1].body, '原评论')
    c.close()
  }
})

test('缓存停用不读取新目标，恢复只读一次；校验中停用禁止评论写入', async () => {
  let reads = 0,
    resolve
  const c = await setup({
    listCommentThreads: async () => {
      reads++
      return { rows: [], total: 0 }
    },
  })
  assert.equal(reads, 1)
  c.hooks.activate()
  assert.equal(reads, 1)
  c.state.body.value = '内容'
  c.state.form.value = {
    validate: () =>
      new Promise((done) => {
        resolve = done
      }),
  }
  const pending = c.state.mutate('save')
  c.hooks.deactivate()
  resolve(true)
  await pending
  assert.equal(c.calls.length, 0)
  c.target.value = { outputId: 'other' }
  await tick()
  await c.state.loadThreads()
  assert.equal(reads, 1)
  c.hooks.activate()
  await tick()
  assert.equal(reads, 2)
  c.close()
})

test('编辑快照保留原修订，权限变化清理旧评论并重读', async () => {
  let reads = 0
  const c = await setup({
    listCommentThreads: async () => {
      reads++
      return { rows: [], total: 0 }
    },
  })
  const original = { id: '33', revision: '2', body: '旧正文', annotations: [] }
  c.state.edit(original)
  original.revision = '99'
  c.state.body.value = '修改'
  await c.state.mutate('save')
  assert.equal(c.calls[0][1].revision, '2')
  c.state.rows.value = [original]
  c.auth.user = { permissions: ['comment:read'] }
  await tick()
  assert.equal(c.state.rows.value.length, 0)
  assert.equal(c.state.body.value, '')
  assert.equal(reads, 2)
  c.close()
})

test('发表评论成功跳至最新页，编辑和删除保持当前页且不重复读取目标页', async () => {
  const pages = []
  let total = 31
  const c = await setup({
    listComments: async (id, page) => {
      pages.push(page)
      return { rows: [{ id: String(page) }], total }
    },
  })
  pages.length = 0
  c.state.body.value = '最新回复'
  await c.state.mutate('save')
  await tick()
  assert.equal(c.state.page.value, 2)
  assert.deepEqual(pages, [1, 2])
  assert.equal(c.state.rows.value[0].id, '2')
  pages.length = 0
  c.state.edit({ id: '33', revision: '1', body: '旧正文', annotations: [] })
  c.state.body.value = '改正文'
  await c.state.mutate('save')
  assert.deepEqual(pages, [2])
  pages.length = 0
  await c.state.mutate('delete', { id: '33', revision: '2' })
  assert.deepEqual(pages, [2])
  pages.length = 0
  c.state.threadId.value = 'another'
  await tick()
  assert.deepEqual(pages, [1])
  c.state.page.value = 2
  await tick()
  total = 0
  pages.length = 0
  await c.state.refresh()
  assert.deepEqual(pages, [2, 1])
  assert.equal(c.state.page.value, 1)
  c.close()
})

test('只读评论权限不允许新建或回复，撤销阅读后不继续读取或恢复旧正文', async () => {
  let threads = 0,
    posts = 0,
    reads = 0
  const c = await setup({
    createCommentThread: async () => {
      threads++
      return { data: { id: '12' } }
    },
    postComment: async () => {
      posts++
      return { data: { id: '13' } }
    },
    listCommentThreads: async () => {
      reads++
      return { rows: [], total: 0 }
    },
  })
  c.auth.user.permissions = ['comment:read']
  await tick()
  assert.equal(c.state.canCreate.value, false)
  assert.equal(c.state.canRead.value, true)
  await c.state.mutate('thread')
  c.state.threadId.value = '12'
  c.state.body.value = '不得提交'
  await c.state.mutate('save')
  c.state.reply({ id: '13', body: '旧正文' })
  assert.equal(c.state.parent.value, undefined)
  assert.equal(threads, 0)
  assert.equal(posts, 0)
  c.auth.user.permissions = []
  await tick()
  const before = reads
  await c.state.loadThreads()
  assert.equal(reads, before)
  assert.equal(c.state.body.value, '')
  assert.equal(c.state.canRead.value, false)
  c.close()
})

test('表单校验期间撤销创建权限不发表评论', async () => {
  const c = await setup()
  let resolve
  c.state.body.value = '待提交'
  c.state.form.value = {
    validate: () =>
      new Promise((done) => {
        resolve = done
      }),
  }
  const pending = c.state.mutate('save')
  c.auth.user.permissions = ['comment:read']
  resolve(true)
  await pending
  assert.equal(c.calls.length, 0)
  c.close()
})

test('未知发帖撤权后允许离开但保留原意图，恢复权限后按原键核对', async () => {
  const calls = []
  const c = await setup({
    postComment: async (...args) => {
      calls.push(args)
      if (calls.length === 1) throw new ApiError('超时', 408)
      return { data: { id: '13' } }
    },
  })
  c.state.body.value = '待核对'
  await c.state.mutate('save')
  assert.equal(await c.state.confirmLeave(), false)
  c.auth.user.permissions = ['comment:read']
  await tick()
  assert.equal(c.state.retryBlocked.value, true)
  assert.equal(await c.state.confirmLeave(), true)
  await c.state.retry()
  assert.equal(calls.length, 1)
  c.auth.user.permissions = ['*:*:*']
  await tick()
  assert.equal(c.state.retryBlocked.value, false)
  await c.state.retry()
  assert.equal(calls.length, 2)
  assert.equal(calls[0][2], calls[1][2])
  assert.equal(calls[1][1].body, '待核对')
  c.close()
})

test('登录失效时评论守卫允许退出，不阻塞登录路由', async () => {
  const c = await setup()
  c.state.body.value = '旧账号草稿'
  c.auth.token = ''
  assert.equal(await c.state.confirmLeave(), true)
  assert.equal(await c.hooks.update({ fullPath: '/login' }, { fullPath: '/project' }), true)
  c.close()
})

test('刷新关闭保护未发送正文和标注，隐藏撤权及卸载不拦截退出', async () => {
  const c = await setup()
  function prevented() {
    let blocked = false
    c.hooks.beforeunload?.({ preventDefault() { blocked = true }, returnValue: undefined })
    return blocked
  }
  assert.equal(prevented(), false)
  c.state.body.value = '未发送正文'; assert.equal(prevented(), true)
  c.state.resetEditor(); c.state.updateAnnotations([{ shape: 'point' }])
  assert.equal(prevented(), true)
  c.hooks.deactivate(); assert.equal(prevented(), false)
  c.hooks.activate(); c.state.body.value = '返回后的正文'; assert.equal(prevented(), true)
  c.auth.user.permissions = []; assert.equal(prevented(), false)
  c.close(); assert.equal(c.hooks.beforeunload, undefined)
})

test('评论发送中及结果未知时刷新提示，确认原请求成功后解除', async () => {
  let reject, calls = 0
  const c = await setup({ postComment: () => { calls++; return calls === 1 ? new Promise((_resolve, fail) => { reject = fail }) : Promise.resolve({ data: { id: '13' } }) } })
  const prevented = () => {
    let blocked = false
    c.hooks.beforeunload({ preventDefault() { blocked = true } })
    return blocked
  }
  c.state.body.value = '待发送'
  const first = c.state.mutate('save'); await tick()
  assert.equal(c.state.saving.value, true); assert.equal(prevented(), true)
  reject(new Error('响应丢失')); await first
  assert.equal(c.state.uncertain.value, true); assert.equal(prevented(), true)
  await c.state.retry(); assert.equal(prevented(), false)
  c.close()
})

test('评论页签隐藏保留未发送正文和标注，返回刷新且旧放弃确认失效',async()=>{
 let confirm
 const c=await setup({confirm:()=>new Promise(resolve=>{confirm=resolve})})
 c.state.body.value='保留正文';c.state.videoTime.value='1.25';c.state.updateAnnotations([{shape:'point'}])
 const leave=c.state.confirmLeave();c.visible.value=false
 await c.state.mutate('save');assert.equal(c.calls.length,0)
 c.visible.value=true;confirm();assert.equal(await leave,false);await tick()
 assert.equal(c.state.body.value,'保留正文');assert.equal(c.state.videoTime.value,'1.25')
 assert.equal(c.state.annotations.value.length,1);assert.equal(c.state.threadId.value,'12')
 c.close()
})

test('侧栏首次发送自动创建讨论并保留正文和时间点', async () => {
  let created = 0
  const c = await setup({ createCommentThread: async () => { created++; return { data: { id: '88' } } } })
  c.state.threadId.value = ''
  c.state.body.value = '第一条评论'; c.state.videoTime.value = '2.5'
  await c.state.sendFromSidebar()
  assert.equal(created, 1); assert.equal(c.calls.length, 1)
  assert.equal(c.calls[0][0], '88'); assert.equal(c.calls[0][1].body, '第一条评论'); assert.equal(c.calls[0][1].videoTime, '2.5')
  c.close()
})
test('侧栏创建讨论期间切换素材，不发送或恢复旧正文', async () => {
  let resolve
  const c = await setup({ createCommentThread: () => new Promise(done => { resolve = done }) })
  c.state.threadId.value = ''; c.state.body.value = '旧素材评论'
  const sending = c.state.sendFromSidebar(); c.target.value = { outputId: 'new' }; resolve({ data: { id: '88' } }); await sending
  assert.equal(c.calls.length, 0); assert.equal(c.state.body.value, ''); c.close()
})

test('侧栏独立评论建立独立讨论，回复继续使用原讨论', async () => {
  let created=0
  const c=await setup({createCommentThread:async()=>({data:{id:String(80+ ++created)}})})
  c.state.body.value='第一处';await c.state.sendFromSidebar(true)
  c.state.body.value='第二处';await c.state.sendFromSidebar(true)
  assert.equal(created,2);assert.equal(c.calls[0][0],'81');assert.equal(c.calls[1][0],'82')
  c.state.reply({id:'22',threadId:'82',annotations:[]});c.state.body.value='回复';await c.state.sendFromSidebar(true)
  assert.equal(created,2);assert.equal(c.calls[2][1].parentId,'22');c.close()
})
test('侧栏校验失败后重发不重复创建讨论', async()=>{
  let created=0
  const c=await setup({createCommentThread:async()=>{created++;return {data:{id:'88'}}}})
  c.state.body.value='测试';c.state.form.value={validate:async()=>false}
  await c.state.sendFromSidebar(true)
  c.state.form.value={validate:async()=>true};await c.state.sendFromSidebar(true)
  assert.equal(created,1);assert.equal(c.calls.length,1);c.close()
})
