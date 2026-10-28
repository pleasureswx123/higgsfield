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
test('PDF快速翻页取消旧渲染，关闭清理画布与解析任务', async () => {
  const exports = {},
    renders = [],
    hooks = {},
    drawn = []
  let destroyed = 0,
    imports = 0
  const doc = {
    numPages: 3,
    getPage: async (number) => ({
      getViewport: () => ({ width: 200, height: 300 }),
      render: (options) => {
        let complete
        const item = {
          number,
          options,
          cancel() {
            item.cancelled = true
          },
          promise: new Promise((resolve) => {
            complete = resolve
          }),
        }
        item.resolve = complete
        renders.push(item)
        return item
      },
    }),
  }
  // 显式延迟渲染，验证旧页面即使完成也不能覆盖新页。
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/usePdfPreview.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS } },
    ).outputText,
    {
      exports,
      Uint8Array,
      window: { devicePixelRatio: 1, document: { createElement: () => ({}) } },
      require(name) {
        if (name === 'vue')
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
        if (name === 'pdfjs-dist') imports++
        if (name.endsWith('?url')) return { default: 'worker-url' }
        return {
          GlobalWorkerOptions: {},
          getDocument: () => ({
            promise: Promise.resolve(doc),
            async destroy() {
              destroyed++
            },
          }),
        }
      },
    },
  )
  const source = vue.shallowRef(null),
    canvas = vue.shallowRef({
      style: {},
      width: 0,
      getContext: () => ({ drawImage: (image) => drawn.push(image) }),
    })
  const scope = vue.effectScope(),
    state = scope.run(() => exports.usePdfPreview(() => source.value, canvas))
  await tick()
  assert.equal(imports, 0)
  source.value = new Blob(['pdf'])
  await tick()
  assert.equal(imports, 1)
  assert.equal(state.total.value, 3)
  state.page.value = 2
  await tick()
  assert.equal(renders[0].cancelled, true)
  renders[1].resolve()
  await tick()
  renders[0].resolve()
  await tick()
  assert.equal(drawn.length, 1)
  assert.equal(drawn[0], renders[1].options.canvas)
  hooks.deactivate()
  assert.equal(destroyed, 1)
  assert.equal(canvas.value.width, 0)
  hooks.activate()
  await tick()
  assert.equal(state.total.value, 3)
  assert.equal(state.page.value, 1)
  renders.at(-1).resolve()
  await tick()
  hooks.unmount()
  assert.equal(destroyed, 2)
  assert.equal(canvas.value.width, 0)
  scope.stop()
})

test('PDF解析器延迟加载期间关闭文件，不启动旧解析；重新打开可正常加载', async () => {
  const exports = {},
    hooks = {}
  let resolveLibrary,
    opened = 0
  const library = new Promise((resolve) => {
    resolveLibrary = resolve
  })
  runInNewContext(
    ts.transpileModule(
      readFileSync(join(__dirname, '../src/composables/usePdfPreview.ts'), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS } },
    ).outputText,
    {
      exports,
      Uint8Array,
      require(name) {
        if (name === 'vue')
          return {
            ...vue,
            onActivated: (fn) => (hooks.activate = fn),
            onDeactivated: (fn) => (hooks.deactivate = fn),
            onBeforeUnmount: (fn) => (hooks.unmount = fn),
          }
        if (name === 'pdfjs-dist') return library
        if (name.endsWith('?url')) return { default: 'worker-url' }
        return { pdfAssetBase: '/pdf-assets/' }
      },
    },
  )
  const source = vue.shallowRef(new Blob(['first'])),
    scope = vue.effectScope()
  const state = scope.run(() => exports.usePdfPreview(() => source.value, vue.shallowRef()))
  await tick()
  source.value = null
  await tick()
  resolveLibrary({
    GlobalWorkerOptions: {},
    getDocument: () => {
      opened++
      return { promise: Promise.resolve({ numPages: 2 }), destroy: async () => {} }
    },
  })
  await tick()
  assert.equal(opened, 0)
  assert.equal(state.total.value, 0)
  assert.equal(state.loading.value, false)
  source.value = new Blob(['second'])
  await tick()
  assert.equal(opened, 1)
  assert.equal(state.total.value, 2)
  hooks.unmount()
  scope.stop()
})
