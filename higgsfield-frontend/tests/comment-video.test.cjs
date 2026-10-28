const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { join } = require('node:path')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'),
  vue = require('vue')
function setup(api = {}, kind = 'Video') {
  const exports = {},
    helpers = {},
    hooks = {},
    visible = vue.ref(true),
    auth = vue.reactive({ token: 'one' }),
    target = vue.ref({ outputId: '9' }),
    revoked = []
  runInNewContext(
    ts.transpileModule(readFileSync(join(__dirname, '../src/utils/commentVideoTime.ts'), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    { exports: helpers },
  )
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, `../src/composables/useComment${kind}.ts`), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS } },
    ).outputText,
    {
      exports,
      AbortController,
      URL: { createObjectURL: () => 'blob:video', revokeObjectURL: (value) => revoked.push(value) },
      require(id) {
        if (id === 'vue')
          return {
            ...vue,
            onBeforeUnmount: (fn) => {
              hooks.unmount = fn
            },
            onDeactivated: (fn) => {
              hooks.deactivate = fn
            },
            onActivated: (fn) => {
              hooks.activate = fn
            },
          }
        if (id === '@/stores/auth') return { useAuthStore: () => auth }
        if (id === '@/utils/commentVideoTime') return helpers
        return api
      },
    },
  )
  const scope = vue.effectScope(),
    state = scope.run(() => exports[`useComment${kind}`](() => target.value, () => visible.value))
  return {
    visible,
    state,
    target,
    auth,
    revoked,
    hooks,
    close: () => {
      hooks.unmount()
      scope.stop()
    },
  }
}
test('点击定位按固定输出ID读取，等待元数据后暂停定位且拒绝超时长', async () => {
  const ids = [],
    c = setup({
      getOutputMedia: async (id) => {
        ids.push(id)
        return {}
      },
    })
  let paused = 0
  c.state.player.value = {
    readyState: 0,
    duration: 20,
    currentTime: 0,
    pause: () => {
      paused++
    },
  }
  await c.state.open('12.345678')
  assert.deepEqual(ids, ['9'])
  assert.equal(c.state.player.value.currentTime, 0)
  c.state.player.value.readyState = 1
  c.state.seekReady()
  assert.equal(c.state.player.value.currentTime, 12.345678)
  assert.equal(paused, 1)
  await c.state.open('21')
  assert.ok(c.state.error.value)
  assert.equal(c.state.player.value.currentTime, 12.345678)
  c.auth.token = 'two'
  assert.equal(c.state.url.value, '')
  assert.deepEqual(c.revoked, ['blob:video'])
  c.close()
})

for (const kind of ['Image', 'Video']) {
  test(`${kind} 同值目标重渲染保留媒体，目标或账号改变才清理`, async () => {
    let reads = 0
    const c = setup(
      {
        getOutputMedia: async () => {
          reads++
          return {}
        },
      },
      kind,
    )
    await c.state.open()
    c.target.value = { outputId: '9' }
    await vue.nextTick()
    assert.equal(c.state.url.value, 'blob:video')
    assert.deepEqual(c.revoked, [])
    await c.state.open()
    assert.equal(reads, 1)
    c.target.value = { outputId: '10' }
    assert.equal(c.state.url.value, '')
    await c.state.open()
    assert.equal(reads, 2)
    c.auth.token = 'two'
    assert.equal(c.state.url.value, '')
    assert.equal(c.revoked.length, 2)
    c.close()
  })
}
test('切换固定目标时取消旧媒体请求，迟到结果不创建URL', async () => {
  let resolve, signal
  const c = setup({
    getOutputMedia: (id, download, current) => {
      signal = current
      return new Promise((done) => {
        resolve = done
      })
    },
  })
  const pending = c.state.open('0')
  c.target.value = { assetVersionId: '22' }
  assert.equal(signal.aborted, true)
  resolve({})
  await pending
  assert.equal(c.state.url.value, '')
  c.close()
})

for (const kind of ['Image', 'Video']) {
  test(`${kind} 停用阻止读取，权限变化释放媒体，迟到响应不得恢复`, async () => {
    let resolve,
      reads = 0
    const c = setup(
      {
        getOutputMedia: async () => {
          reads++
          if (reads === 2)
            return new Promise((done) => {
              resolve = done
            })
          return {}
        },
      },
      kind,
    )
    await c.state.open()
    c.hooks.deactivate()
    assert.equal(c.state.url.value, '')
    assert.equal(c.revoked.length, 1)
    await c.state.open()
    assert.equal(reads, 1)
    c.hooks.activate()
    const pending = c.state.open()
    await Promise.resolve()
    c.auth.user = { permissions: ['changed'] }
    resolve({})
    await pending
    assert.equal(c.state.url.value, '')
    assert.equal(c.state.loading.value, false)
    await c.state.open()
    assert.equal(reads, 3)
    assert.equal(c.state.url.value, 'blob:video')
    c.close()
    await c.state.open()
    assert.equal(reads, 3)
  })
}

test('视频停用暂停播放并清除待定位时间，恢复不得使用旧播放器时间', async () => {
  const c = setup({ getOutputMedia: async () => ({}) })
  let pauses = 0
  c.state.player.value = {
    readyState: 1,
    duration: 20,
    currentTime: 3,
    pause: () => {
      pauses++
    },
  }
  await c.state.open('5')
  assert.equal(c.state.currentTime(), '5')
  c.hooks.deactivate()
  assert.ok(pauses >= 2)
  assert.equal(c.state.currentTime(), '')
  c.hooks.activate()
  c.state.seekReady()
  assert.equal(c.state.currentTime(), '')
  c.close()
})

for (const kind of ['Image','Video']) {
 test(`${kind} 页签隐藏取消读取，缓存未激活不恢复，返回按原媒体重新读取`,async()=>{
  const requests=[]
  const c=setup({getOutputMedia:(...args)=>new Promise(resolve=>requests.push({args,resolve}))},kind)
  const open=c.state.open();assert.equal(requests.length,1)
  c.visible.value=false;assert.equal(requests[0].args[2].aborted,true)
  requests[0].resolve({});await open;assert.equal(c.state.url.value,'')
  await c.state.open();assert.equal(requests.length,1)
  c.hooks.deactivate();c.visible.value=true;await c.state.open();assert.equal(requests.length,1)
  c.hooks.activate();const reopened=c.state.open();assert.equal(requests.length,2)
  assert.equal(requests[1].args[0],'9');requests[1].resolve({});await reopened
  assert.equal(c.state.url.value,'blob:video');c.visible.value=false
  assert.equal(c.state.url.value,'');assert.deepEqual(c.revoked,['blob:video']);c.close()
 })
}
