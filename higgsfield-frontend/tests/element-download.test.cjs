const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs'),
  { join } = require('node:path'),
  { runInNewContext } = require('node:vm')
const ts = require('typescript'),
  vue = require('vue')
const tick = () => new Promise(setImmediate)
function setup() {
  const exports = {},
    calls = [],
    reads = [],
    anchors = [],
    changed = [],
    hooks = {},
    timers = new Map(),
    revoked = []
  const auth = vue.reactive({ token: 'one', user: { permissions: ['asset:download'] } }),
    allowed = vue.ref(true)
  const rows = [
    { id: '9007199254740993', projectId: '99', currentRevisionId: '901', name: '主/角' },
    { id: '2', projectId: '99', currentRevisionId: '902', name: '场景' },
  ]
  let urlId = 0,
    timer = 0
  const details = {}
  for (const item of rows)
    details[item.id] = {
      element: { ...item },
      currentRevision: {
        id: item.currentRevisionId,
        media: [
          { assetVersionId: item.id === '2' ? '201' : '101', ordinal: 0 },
          { assetVersionId: item.id === '2' ? '202' : '102', ordinal: 1 },
        ],
      },
    }
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/useElementDownload.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
    ).outputText,
    {
      exports,
      Error,
      AbortController,
      URL: {
        createObjectURL: () => `blob:${++urlId}`,
        revokeObjectURL: (url) => revoked.push(url),
      },
      setTimeout: (fn) => {
        timers.set(++timer, fn)
        return timer
      },
      clearTimeout: (id) => timers.delete(id),
      document: {
        createElement: () => ({
          click() {
            anchors.push({ href: this.href, name: this.download })
          },
        }),
      },
      require(id) {
        if (id === 'vue')
          return {
            ...vue,
            onActivated: (fn) => {
              hooks.activate = fn
            },
            onDeactivated: (fn) => {
              hooks.deactivate = fn
            },
            onBeforeUnmount: (fn) => {
              hooks.close = fn
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
        if (id.includes('stores/auth')) return { useAuthStore: () => auth }
        if (id.includes('assetFormats')) return { assetExtension: () => '.png' }
        return {
          readElement: async (id, signal) => {
            reads.push({ id, signal })
            return { data: details[id] }
          },
          readMedia: (...args) =>
            new Promise((resolve, reject) => calls.push({ args, resolve, reject })),
        }
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() =>
      exports.useElementDownload(
        () => allowed.value,
        (ids) => changed.push([...ids]),
      ),
    )
  return {
    state,
    rows,
    details,
    calls,
    reads,
    anchors,
    changed,
    hooks,
    auth,
    allowed,
    timers,
    revoked,
    close() {
      hooks.close()
      scope.stop()
    },
  }
}
test('多图按固定版本下载，部分失败重试跳过已交付图片并只清除全部完成的元素', async () => {
  const h = setup(),
    run = h.state.download([h.rows[0], h.rows[0]])
  await tick()
  assert.equal(h.calls[0].args[0], '101')
  assert.equal(h.calls[0].args[1], true)
  assert.equal(h.hooks.leave(), false)
  h.calls[0].args[3](68)
  assert.equal(h.state.loadedBytes.value, 68)
  h.calls[0].resolve({ type: 'image/png' })
  await tick()
  h.calls[1].reject(new Error('无下载权限'))
  await run
  assert.equal(h.anchors[0].name, '主_角-1-101.png')
  assert.deepEqual(h.changed, [])
  assert.match(h.state.message.value, /本次已交给浏览器 1 个图片文件/)
  const retry = h.state.download([h.rows[0]])
  await tick()
  assert.equal(h.calls[2].args[0], '102')
  h.calls[2].resolve({ type: 'image/png' })
  await retry
  assert.equal(h.calls.length, 3)
  assert.deepEqual(h.changed, [['9007199254740993']])
  assert.equal(h.anchors.length, 2)
  for (const release of h.timers.values()) release()
  assert.equal(h.revoked.length, 2)
  h.close()
})
test('空图片、修订变化和非图片内容不触发下载，仍继续处理其他元素', async () => {
  const h = setup()
  h.details[h.rows[0].id].currentRevision.id = '999'
  const run = h.state.download(h.rows)
  await tick()
  assert.equal(h.calls[0].args[0], '201')
  h.calls[0].resolve({ type: 'application/json' })
  await tick()
  h.calls[1].resolve({ type: 'image/png' })
  await run
  assert.equal(h.anchors.length, 1)
  assert.deepEqual(h.changed, [])
  assert.match(h.state.message.value, /元素已变化/)
  assert.match(h.state.message.value, /返回内容不是图片/)
  h.details['2'].currentRevision.media = []
  await h.state.download([h.rows[1]])
  assert.match(h.state.message.value, /没有可下载图片/)
  h.close()
})
test('停止、缓存停用、撤权和账号变化阻断迟到文件及后续下载', async () => {
  const h = setup()
  let run = h.state.download(h.rows)
  await tick()
  h.state.stop()
  assert.equal(h.calls[0].args[2].aborted, true)
  h.calls[0].resolve({ type: 'image/png' })
  await run
  assert.equal(h.calls.length, 1)
  assert.equal(h.anchors.length, 0)
  run = h.state.download(h.rows)
  await tick()
  h.hooks.deactivate()
  h.calls[1].resolve({ type: 'image/png' })
  await run
  await h.state.download(h.rows)
  assert.equal(h.calls.length, 2)
  h.hooks.activate()
  run = h.state.download(h.rows)
  await tick()
  h.allowed.value = false
  h.calls[2].resolve({ type: 'image/png' })
  await run
  assert.equal(h.anchors.length, 0)
  h.allowed.value = true
  run = h.state.download(h.rows)
  await tick()
  h.auth.token = 'two'
  h.calls[3].resolve({ type: 'image/png' })
  await run
  assert.equal(h.state.message.value, '')
  assert.deepEqual(h.changed, [])
  assert.equal(h.state.pending.value, false)
  h.close()
})
