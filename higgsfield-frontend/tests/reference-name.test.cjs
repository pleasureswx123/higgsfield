const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const ts = require('typescript'), vue = require('vue')

test('输入替换同版本引用对象时名称保持稳定，版本或身份变化时重新读取并丢弃旧响应', async () => {
  const output = {}, calls = [], auth = vue.reactive({ token: '账号一', user: { permissions: [] } })
  let cleanup
  runInNewContext(ts.transpileModule(readFileSync('src/composables/useReferenceName.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports: output, AbortController,
    require: name => name === 'vue' ? { ...vue, onBeforeUnmount: fn => { cleanup = fn } }
      : name.includes('stores/auth') ? { useAuthStore: () => auth }
      : { readAssetVersion: (version, signal) => new Promise(resolve => calls.push({ version, signal, resolve })) },
  })
  const item = vue.ref({ assetVersionId: '10' }), scope = vue.effectScope()
  const name = scope.run(() => output.useReferenceName(() => item.value.assetVersionId))
  calls[0].resolve({ data: { name: '机器人.png' } }); await new Promise(setImmediate)
  assert.equal(name.value, '机器人.png')
  for (let i = 0; i < 20; i++) {
    item.value = { assetVersionId: '10' }; await vue.nextTick()
    assert.equal(name.value, '机器人.png')
  }
  assert.equal(calls.length, 1)
  item.value = { assetVersionId: '13' }; await vue.nextTick()
  assert.equal(name.value, ''); assert.equal(calls.length, 2)
  auth.token = '账号二'; await vue.nextTick()
  assert.equal(calls[1].signal.aborted, true)
  calls[1].resolve({ data: { name: '旧账号素材.png' } }); await new Promise(setImmediate)
  assert.equal(name.value, '')
  calls[2].resolve({ data: { name: '新账号素材.png' } }); await new Promise(setImmediate)
  assert.equal(name.value, '新账号素材.png')
  cleanup(); scope.stop()
  assert.equal(calls[2].signal.aborted, true)
})
