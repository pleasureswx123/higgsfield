const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const { randomUUID } = require('node:crypto')
const ts = require('typescript'), vue = require('vue')
function setup(name, api = {}, args = []) {
  const exports = {}, hooks = {}, auth = vue.reactive({ token: 'one' }), revoked = []
  runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/composables/' + name + '.ts'), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, AbortController, crypto: { randomUUID }, URL: { createObjectURL: () => 'blob:test', revokeObjectURL: url => revoked.push(url) },
    require(id) {
      if (id === 'vue') return { ...vue, onActivated: fn => { hooks.activate = fn }, onDeactivated: fn => { hooks.deactivate = fn }, onBeforeUnmount: fn => { hooks.unmount = fn } }
      if (id === '@/stores/auth') return { useAuthStore: () => auth }
      if (id === 'vue-router') return { useRouter: () => ({ push: async () => {} }) }
      return api
    },
  })
  const scope = vue.effectScope(), state = scope.run(() => exports[name](...args))
  return { state, hooks, auth, revoked, close: () => { hooks.unmount(); scope.stop() } }
}
test('收藏失败重试复用幂等键，成功后禁止重复提交，切换目标换键', async () => {
  const calls = [], target = vue.ref({ elementId: '9007199254740993' })
  const current = setup('useFavoriteAction', { saveFavorite: async (...args) => {
    calls.push(args); if (calls.length === 1) throw Error('断网')
  } }, [() => target.value])
  await current.state.save(); await current.state.save(); await current.state.save()
  assert.equal(calls.length, 2); assert.equal(calls[0][1], calls[1][1])
  target.value = { assetId: '22' }; await current.state.save()
  assert.notEqual(calls[1][1], calls[2][1]); current.close()
})
test('收藏中的账号切换立即清除状态并丢弃旧成功响应', async () => {
  let resolve, signal
  const current = setup('useFavoriteAction', { saveFavorite: (target, key, s) => { signal = s; return new Promise(done => { resolve = done }) } }, [() => ({ outputId: '23' })])
  const pending = current.state.save(); current.auth.token = 'two'
  assert.equal(signal.aborted, true); resolve(); await pending
  assert.equal(current.state.saved.value, false); assert.equal(current.state.pending.value, false); current.close()
})
test('收藏列表离开页面后丢弃迟到响应，筛选重置分页', async () => {
  let resolve
  const calls = []
  const current = setup('useFavorites', { listFavorites: (...args) => { calls.push(args); return new Promise(done => { resolve = done }) } })
  current.hooks.activate(); current.hooks.deactivate()
  resolve({ rows: [{ id: 'private' }], total: 1 }); await vue.nextTick()
  assert.equal(current.state.rows.value.length, 0); assert.equal(calls[0][2].aborted, true)
  current.hooks.activate(); current.state.page.value = 3; await vue.nextTick()
  current.state.kind.value = 'asset'; await vue.nextTick()
  assert.equal(calls.at(-1)[0], 1); assert.equal(calls.at(-1)[1], 'asset'); current.close()
})
test('取消失败后重试复用键且成功后刷新列表', async () => {
  const calls = []
  const current = setup('useFavorites', {
    listFavorites: async () => ({ rows: [], total: 0 }),
    cancelFavorite: async (...args) => { calls.push(args); if (calls.length === 1) throw Error('断网') },
  })
  await current.state.remove('23'); assert.ok(current.state.error.value)
  await current.state.remove('23'); assert.equal(calls[0][1], calls[1][1]); assert.equal(current.state.error.value, '')
  current.close()
})
test('不可用收藏不读取素材，关闭预览中断详情请求，账号变化释放媒体URL', async () => {
  let resolve, reads = 0, media = 0
  const current = setup('useFavoritePreview', {
    readAsset: () => { reads++; return new Promise(done => { resolve = done }) },
    readMedia: async () => { media++; return {} },
  })
  const row = { target: { assetId: '2' }, available: true, source: { name: '素材' } }
  await current.state.open({ ...row, available: false }); assert.equal(reads, 0)
  const pending = current.state.open(row); current.state.clear()
  resolve({ data: { name: '敏感素材', mediaType: 'image', currentVersionId: '3' } }); await pending
  assert.equal(media, 0); assert.equal(current.state.title.value, '')
  const next = current.state.open(row); resolve({ data: { name: '素材', mediaType: 'image', currentVersionId: '3' } }); await next
  assert.equal(current.state.url.value, 'blob:test'); current.auth.token = 'two'
  assert.deepEqual(current.revoked, ['blob:test']); assert.equal(current.state.url.value, ''); current.close()
})

test('作品收藏直接读取目标输出，不要求任务详情权限；未归档不请求媒体', async () => {
  const ids = [], media = []
  const current = setup('useFavoritePreview', {
    getOutput: async id => { ids.push(id); return { data: { ordinal: 1, kind: 'image', archiveState: 'archiving' } } },
    getOutputMedia: async (...args) => { media.push(args); return {} },
  })
  await current.state.open({ target: { outputId: '9007199254740993' }, available: true, source: { jobId: '99' } })
  assert.deepEqual(ids, ['9007199254740993']); assert.equal(media.length, 0)
  assert.ok(current.state.notice.value); assert.equal(current.state.title.value, '作品 #2'); current.close()
})

test('文本作品保留原文，已归档媒体只按输出ID请求，停用后释放', async () => {
  let output = { ordinal: 0, kind: 'text', text: '<script>原文</script>' }
  const media = []
  const current = setup('useFavoritePreview', {
    getOutput: async () => ({ data: output }),
    getOutputMedia: async (...args) => { media.push(args); return {} },
  })
  const row = { target: { outputId: '22' }, available: true, source: {} }
  await current.state.open(row); assert.equal(current.state.text.value, output.text)
  output = { ordinal: 0, kind: 'video', previewUrl: 'https://不应直连.example/file' }
  await current.state.open(row); assert.equal(current.state.text.value, '')
  assert.equal(media[0][0], '22'); assert.equal(media[0][1], false)
  current.hooks.deactivate(); assert.equal(current.state.url.value, ''); assert.deepEqual(current.revoked, ['blob:test']); current.close()
})
